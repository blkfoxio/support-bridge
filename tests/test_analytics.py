"""Tests for analytics service and KPI endpoints."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.analytics.services import AnalyticsService, parse_period
from apps.audit.factories import EventLogFactory
from apps.conversations.factories import AssignmentFactory, ConversationFactory
from apps.conversations.models import Conversation, ConversationStatus
from apps.messaging.factories import MessageFactory
from apps.queues.factories import AnalystProfileFactory, QueueFactory


@pytest.mark.django_db
class TestParseperiod:
    def test_hours(self):
        start, end = parse_period("6h")
        assert (end - start).total_seconds() == pytest.approx(6 * 3600, abs=2)

    def test_days(self):
        start, end = parse_period("7d")
        assert (end - start).total_seconds() == pytest.approx(7 * 86400, abs=2)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_period("abc")


@pytest.mark.django_db
class TestQueueDepth:
    def test_counts_only_open(self):
        queue = QueueFactory(key="test-depth")
        now = timezone.now()
        # Open conversations
        ConversationFactory(queue=queue, status=ConversationStatus.QUEUED)
        ConversationFactory(queue=queue, status=ConversationStatus.ASSIGNED)
        ConversationFactory(queue=queue, status=ConversationStatus.NEW)
        # Closed conversations — should not be counted
        ConversationFactory(queue=queue, status=ConversationStatus.RESOLVED)
        ConversationFactory(queue=queue, status=ConversationStatus.CLOSED)

        result = AnalyticsService.queue_depth(queue_id=queue.pk)
        assert len(result) == 1
        assert result[0]["queue_key"] == "test-depth"
        assert result[0]["count"] == 3

    def test_empty_queue(self):
        queue = QueueFactory(key="empty-queue")
        result = AnalyticsService.queue_depth(queue_id=queue.pk)
        assert result == []


@pytest.mark.django_db
class TestMedianFirstResponse:
    def test_correct_median(self):
        queue = QueueFactory(key="median-test")
        now = timezone.now()
        base = now - timedelta(hours=2)

        # Create 3 conversations with known first response deltas: 60s, 120s, 180s
        for delta_seconds in [60, 120, 180]:
            conv = ConversationFactory(queue=queue, status=ConversationStatus.ASSIGNED)
            Conversation.objects.filter(pk=conv.pk).update(
                opened_at=base,
                first_response_at=base + timedelta(seconds=delta_seconds),
            )

        period_start = now - timedelta(hours=3)
        period_end = now
        result = AnalyticsService.median_first_response(queue.pk, period_start, period_end)
        assert result == 120.0  # median of [60, 120, 180]

    def test_none_when_empty(self):
        queue = QueueFactory(key="empty-median")
        now = timezone.now()
        result = AnalyticsService.median_first_response(
            queue.pk, now - timedelta(hours=1), now
        )
        assert result is None


@pytest.mark.django_db
class TestMedianResolutionTime:
    def test_correct_median(self):
        queue = QueueFactory(key="res-median")
        now = timezone.now()
        base = now - timedelta(hours=2)

        for delta_seconds in [300, 600, 900]:
            conv = ConversationFactory(queue=queue, status=ConversationStatus.RESOLVED)
            Conversation.objects.filter(pk=conv.pk).update(
                opened_at=base,
                resolved_at=base + timedelta(seconds=delta_seconds),
            )

        result = AnalyticsService.median_resolution_time(
            queue.pk, now - timedelta(hours=3), now
        )
        assert result == 600.0


@pytest.mark.django_db
class TestSlaBreachCount:
    def test_counts_breaches(self):
        queue = QueueFactory(
            key="sla-test",
            sla_first_response_seconds=300,
            sla_resolution_seconds=3600,
        )
        now = timezone.now()
        base = now - timedelta(hours=2)

        # Breaching first response SLA (400s > 300s)
        conv1 = ConversationFactory(queue=queue, status=ConversationStatus.ASSIGNED)
        Conversation.objects.filter(pk=conv1.pk).update(
            opened_at=base,
            first_response_at=base + timedelta(seconds=400),
        )

        # Not breaching (200s < 300s)
        conv2 = ConversationFactory(queue=queue, status=ConversationStatus.ASSIGNED)
        Conversation.objects.filter(pk=conv2.pk).update(
            opened_at=base,
            first_response_at=base + timedelta(seconds=200),
        )

        # Breaching resolution SLA (4000s > 3600s)
        conv3 = ConversationFactory(queue=queue, status=ConversationStatus.RESOLVED)
        Conversation.objects.filter(pk=conv3.pk).update(
            opened_at=base,
            resolved_at=base + timedelta(seconds=4000),
        )

        result = AnalyticsService.sla_breach_count(
            queue.pk, now - timedelta(hours=3), now
        )
        assert result == 2

    def test_no_sla_returns_zero(self):
        queue = QueueFactory(
            key="no-sla",
            sla_first_response_seconds=None,
            sla_resolution_seconds=None,
        )
        result = AnalyticsService.sla_breach_count(
            queue.pk, timezone.now() - timedelta(hours=1), timezone.now()
        )
        assert result == 0


@pytest.mark.django_db
class TestTransferRate:
    def test_calculation(self):
        queue = QueueFactory(key="transfer-test")
        now = timezone.now()
        base = now - timedelta(hours=2)

        # 4 conversations, 1 transferred
        convs = []
        for _ in range(4):
            c = ConversationFactory(queue=queue)
            Conversation.objects.filter(pk=c.pk).update(opened_at=base)
            convs.append(c)

        # Create transfer event for the first conversation
        EventLogFactory(
            event_type="conversation.transferred",
            conversation=convs[0],
            source="ops_api",
        )

        result = AnalyticsService.transfer_rate(
            queue.pk, now - timedelta(hours=3), now + timedelta(hours=1)
        )
        assert result == 0.25  # 1/4

    def test_no_conversations_returns_none(self):
        queue = QueueFactory(key="no-transfer")
        result = AnalyticsService.transfer_rate(
            queue.pk, timezone.now() - timedelta(hours=1), timezone.now()
        )
        assert result is None


@pytest.mark.django_db
class TestAnalystHandledCount:
    def test_counts_distinct_conversations(self):
        analyst = AnalystProfileFactory(external_user_id="handled-test")
        queue = QueueFactory(key="handled-q")
        now = timezone.now()

        conv1 = ConversationFactory(queue=queue)
        conv2 = ConversationFactory(queue=queue)
        AssignmentFactory(conversation=conv1, analyst=analyst)
        AssignmentFactory(conversation=conv2, analyst=analyst)

        result = AnalyticsService.analyst_handled_count(
            now - timedelta(hours=1), now + timedelta(hours=1)
        )
        analyst_row = next((r for r in result if r["analyst_id"] == "handled-test"), None)
        assert analyst_row is not None
        assert analyst_row["handled_count"] == 2


@pytest.mark.django_db
class TestHourlyVolume:
    def test_groups_by_hour(self):
        queue = QueueFactory(key="hourly-test")
        now = timezone.now()
        base = now.replace(minute=0, second=0, microsecond=0)

        # 2 conversations in the same hour
        for _ in range(2):
            conv = ConversationFactory(queue=queue)
            Conversation.objects.filter(pk=conv.pk).update(opened_at=base - timedelta(minutes=30))

        # 1 conversation in the previous hour
        conv = ConversationFactory(queue=queue)
        Conversation.objects.filter(pk=conv.pk).update(opened_at=base - timedelta(hours=1, minutes=30))

        result = AnalyticsService.hourly_volume(now - timedelta(hours=3), now)
        assert len(result) == 2
        counts = sorted([r["count"] for r in result])
        assert counts == [1, 2]


# --- Endpoint tests ---


@pytest.mark.django_db
class TestQueueMetricsEndpoint:
    def test_returns_200(self, ops_client):
        queue = QueueFactory(key="metrics-ep", sla_first_response_seconds=300, sla_resolution_seconds=3600)
        ConversationFactory(queue=queue, status=ConversationStatus.QUEUED)

        url = reverse("ops-api:queue-metrics", kwargs={"queue_id": queue.pk})
        response = ops_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["queue_key"] == "metrics-ep"
        assert data["queue_depth"] == 1
        assert "median_first_response_seconds" in data
        assert "sla_breach_count" in data
        assert data["period"] == "24h"

    def test_404_nonexistent(self, ops_client):
        url = reverse("ops-api:queue-metrics", kwargs={"queue_id": 99999})
        response = ops_client.get(url)
        assert response.status_code == 404

    def test_requires_auth(self, api_client):
        queue = QueueFactory(key="auth-test-metrics")
        url = reverse("ops-api:queue-metrics", kwargs={"queue_id": queue.pk})
        response = api_client.get(url)
        assert response.status_code in (401, 403)

    def test_accepts_period_param(self, ops_client):
        queue = QueueFactory(key="period-test")
        url = reverse("ops-api:queue-metrics", kwargs={"queue_id": queue.pk})
        response = ops_client.get(url, {"period": "7d"})
        assert response.status_code == 200
        assert response.json()["period"] == "7d"

    def test_invalid_period(self, ops_client):
        queue = QueueFactory(key="bad-period")
        url = reverse("ops-api:queue-metrics", kwargs={"queue_id": queue.pk})
        response = ops_client.get(url, {"period": "abc"})
        assert response.status_code == 400


@pytest.mark.django_db
class TestDashboardEndpoint:
    def test_returns_200(self, ops_client):
        queue = QueueFactory(key="dash-test")
        ConversationFactory(queue=queue, status=ConversationStatus.QUEUED)

        url = reverse("analytics:dashboard")
        response = ops_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert "queue_depths" in data
        assert "hourly_volume" in data
        assert "reopen_rate" in data
        assert data["period"] == "24h"

    def test_requires_auth(self, api_client):
        url = reverse("analytics:dashboard")
        response = api_client.get(url)
        assert response.status_code in (401, 403)
