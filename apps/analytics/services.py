"""Analytics service — KPI computation."""

import logging
import re
import statistics
from datetime import timedelta

from django.db import connection
from django.db.models import Count, F, ExpressionWrapper, DurationField
from django.db.models.functions import TruncHour
from django.utils import timezone

from apps.audit.models import EventLog
from apps.conversations.models import Conversation, ConversationStatus, Assignment
from apps.queues.models import Queue


logger = logging.getLogger(__name__)

PERIOD_RE = re.compile(r"^(\d+)(h|d)$")

CLOSED_STATUSES = {ConversationStatus.RESOLVED, ConversationStatus.CLOSED}


def _is_postgres():
    return connection.vendor == "postgresql"


def parse_period(period_str: str) -> tuple:
    """Convert '1h', '6h', '24h', '7d', '30d' to (start, end) datetimes."""
    match = PERIOD_RE.match(period_str)
    if not match:
        raise ValueError(f"Invalid period format: {period_str}. Use e.g. '24h' or '7d'.")
    value, unit = int(match.group(1)), match.group(2)
    now = timezone.now()
    if unit == "h":
        delta = timedelta(hours=value)
    else:
        delta = timedelta(days=value)
    return (now - delta, now)


def _python_median(values: list[float]) -> float | None:
    """Compute median from a list of floats."""
    if not values:
        return None
    return round(statistics.median(values), 1)


class AnalyticsService:
    """Static methods for KPI queries. All return plain dicts/lists."""

    @staticmethod
    def queue_depth(queue_id=None) -> list[dict]:
        """Count open conversations per queue."""
        qs = Conversation.objects.exclude(status__in=list(CLOSED_STATUSES))
        if queue_id is not None:
            qs = qs.filter(queue_id=queue_id)
        rows = qs.values("queue__key").annotate(count=Count("id")).order_by("queue__key")
        return [{"queue_key": r["queue__key"], "count": r["count"]} for r in rows]

    @staticmethod
    def open_by_queue_status(queue_id=None) -> list[dict]:
        """Open conversations grouped by (queue, status)."""
        qs = Conversation.objects.exclude(status__in=list(CLOSED_STATUSES))
        if queue_id is not None:
            qs = qs.filter(queue_id=queue_id)
        rows = (
            qs.values("queue__key", "status")
            .annotate(count=Count("id"))
            .order_by("queue__key", "status")
        )
        return [
            {"queue_key": r["queue__key"], "status": r["status"], "count": r["count"]}
            for r in rows
        ]

    @staticmethod
    def median_first_response(queue_id, period_start, period_end) -> float | None:
        """Median seconds from opened_at to first_response_at for a queue."""
        logger.debug("median_first_response query", extra={"queue_id": queue_id, "backend": connection.vendor})
        if _is_postgres():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT percentile_cont(0.5) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM first_response_at - opened_at)
                    )
                    FROM conversations_conversation
                    WHERE queue_id = %s
                      AND first_response_at IS NOT NULL
                      AND opened_at >= %s
                      AND opened_at < %s
                    """,
                    [queue_id, period_start, period_end],
                )
                row = cursor.fetchone()
                return round(row[0], 1) if row and row[0] is not None else None

        # Fallback for SQLite / other backends
        convs = Conversation.objects.filter(
            queue_id=queue_id,
            first_response_at__isnull=False,
            opened_at__gte=period_start,
            opened_at__lt=period_end,
        ).values_list("first_response_at", "opened_at")
        deltas = [(fr - opened).total_seconds() for fr, opened in convs]
        return _python_median(deltas)

    @staticmethod
    def median_resolution_time(queue_id, period_start, period_end) -> float | None:
        """Median seconds from opened_at to resolved_at for a queue."""
        logger.debug("median_resolution_time query", extra={"queue_id": queue_id, "backend": connection.vendor})
        if _is_postgres():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT percentile_cont(0.5) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM resolved_at - opened_at)
                    )
                    FROM conversations_conversation
                    WHERE queue_id = %s
                      AND resolved_at IS NOT NULL
                      AND opened_at >= %s
                      AND opened_at < %s
                    """,
                    [queue_id, period_start, period_end],
                )
                row = cursor.fetchone()
                return round(row[0], 1) if row and row[0] is not None else None

        convs = Conversation.objects.filter(
            queue_id=queue_id,
            resolved_at__isnull=False,
            opened_at__gte=period_start,
            opened_at__lt=period_end,
        ).values_list("resolved_at", "opened_at")
        deltas = [(res - opened).total_seconds() for res, opened in convs]
        return _python_median(deltas)

    @staticmethod
    def hourly_volume(period_start, period_end) -> list[dict]:
        """Conversation volume grouped by hour."""
        rows = (
            Conversation.objects.filter(opened_at__gte=period_start, opened_at__lt=period_end)
            .annotate(hour=TruncHour("opened_at"))
            .values("hour")
            .annotate(count=Count("id"))
            .order_by("hour")
        )
        return [{"hour": r["hour"].isoformat(), "count": r["count"]} for r in rows]

    @staticmethod
    def transfer_rate(queue_id, period_start, period_end) -> float | None:
        """Fraction of conversations transferred in a queue during period."""
        total = Conversation.objects.filter(
            queue_id=queue_id,
            opened_at__gte=period_start,
            opened_at__lt=period_end,
        ).count()
        if total == 0:
            return None
        transferred = EventLog.objects.filter(
            event_type="conversation.transferred",
            conversation__queue_id=queue_id,
            created_at__gte=period_start,
            created_at__lt=period_end,
        ).count()
        return round(transferred / total, 4)

    @staticmethod
    def reopen_rate(period_start, period_end) -> float | None:
        """Fraction of closed conversations that were reopened during period."""
        closed = Conversation.objects.filter(
            closed_at__gte=period_start,
            closed_at__lt=period_end,
        ).count()
        if closed == 0:
            return None
        reopened = EventLog.objects.filter(
            event_type="conversation.reopened",
            created_at__gte=period_start,
            created_at__lt=period_end,
        ).count()
        return round(reopened / closed, 4)

    @staticmethod
    def analyst_handled_count(period_start, period_end) -> list[dict]:
        """Distinct conversations handled per analyst during period."""
        rows = (
            Assignment.objects.filter(
                assigned_at__gte=period_start,
                assigned_at__lt=period_end,
            )
            .values("analyst__display_name", "analyst__external_user_id")
            .annotate(handled_count=Count("conversation", distinct=True))
            .order_by("-handled_count")
        )
        return [
            {
                "analyst_name": r["analyst__display_name"],
                "analyst_id": r["analyst__external_user_id"],
                "handled_count": r["handled_count"],
            }
            for r in rows
        ]

    @staticmethod
    def sla_breach_count(queue_id, period_start, period_end) -> int:
        """Count conversations breaching SLA thresholds for a queue."""
        logger.debug("sla_breach_count query", extra={"queue_id": queue_id, "backend": connection.vendor})
        try:
            queue = Queue.objects.get(pk=queue_id)
        except Queue.DoesNotExist:
            return 0

        sla_fr = queue.sla_first_response_seconds
        sla_res = queue.sla_resolution_seconds

        if sla_fr is None and sla_res is None:
            return 0

        if _is_postgres():
            conditions = []
            params = [queue_id, period_start, period_end]

            if sla_fr is not None:
                conditions.append(
                    "(first_response_at IS NOT NULL AND "
                    "EXTRACT(EPOCH FROM first_response_at - opened_at) > %s)"
                )
                params.append(sla_fr)

            if sla_res is not None:
                conditions.append(
                    "(resolved_at IS NOT NULL AND "
                    "EXTRACT(EPOCH FROM resolved_at - opened_at) > %s)"
                )
                params.append(sla_res)

            where_clause = " OR ".join(conditions)

            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM conversations_conversation
                    WHERE queue_id = %s
                      AND opened_at >= %s
                      AND opened_at < %s
                      AND ({where_clause})
                    """,
                    params,
                )
                return cursor.fetchone()[0]

        # Fallback for SQLite
        convs = Conversation.objects.filter(
            queue_id=queue_id,
            opened_at__gte=period_start,
            opened_at__lt=period_end,
        ).values_list("first_response_at", "resolved_at", "opened_at")

        count = 0
        for fr_at, res_at, opened_at in convs:
            if sla_fr is not None and fr_at is not None:
                if (fr_at - opened_at).total_seconds() > sla_fr:
                    count += 1
                    continue
            if sla_res is not None and res_at is not None:
                if (res_at - opened_at).total_seconds() > sla_res:
                    count += 1
        return count
