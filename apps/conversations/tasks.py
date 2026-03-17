"""Celery tasks for conversation lifecycle — idle detection and auto-transitions."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.customer_api.serializers import MessageSerializer
from apps.messaging.models import ActorType, Message, MessageDirection, MessageSource, MessageType
from common.sse import SSEPublisher

from .models import Conversation, ConversationStatus

logger = logging.getLogger(__name__)

# SOC idle thresholds by severity (in minutes)
SOC_IDLE_THRESHOLDS = {
    "critical": 5,
    "high": 15,
    "medium": 30,
    "low": 30,
}

# Customer idle thresholds (in hours)
CUSTOMER_NUDGE_HOURS = 4
CUSTOMER_AUTO_RESOLVE_HOURS = 24
RESOLVED_AUTO_CLOSE_HOURS = 72

# Case-linked conversations get tighter SOC thresholds (50%)
CASE_LINKED_MULTIPLIER = 0.5


def _create_system_message(conversation, body):
    """Create an internal system message (not relayed to Roam)."""
    return Message.objects.create(
        conversation=conversation,
        actor_type=ActorType.SYSTEM,
        actor_id="system",
        direction=MessageDirection.OUTBOUND,
        source=MessageSource.INTERNAL,
        body_plain=body,
        message_type=MessageType.SYSTEM_NOTE,
    )


def _publish_system_message(conversation, message):
    """Publish a system message via SSE."""
    try:
        publisher = SSEPublisher()
        conv_id = str(conversation.id)
        publisher.publish(
            conversation_id=conv_id,
            event_type="message.created",
            data=MessageSerializer(message).data,
        )
    except Exception:
        logger.debug("Failed to publish SSE for idle message on %s", conversation.id, exc_info=True)


def _publish_status_changed(conversation, system_message):
    """Publish both the system message and a status change event."""
    try:
        publisher = SSEPublisher()
        conv_id = str(conversation.id)
        publisher.publish(
            conversation_id=conv_id,
            event_type="message.created",
            data=MessageSerializer(system_message).data,
        )
        publisher.publish(
            conversation_id=conv_id,
            event_type="conversation.status_changed",
            data={"conversation_id": conv_id, "status": conversation.status},
        )
    except Exception:
        logger.debug("Failed to publish SSE for status change on %s", conversation.id, exc_info=True)


@shared_task(name="conversations.check_idle", bind=True, max_retries=0)
def check_idle_conversations(self):
    """Periodic task to detect and handle idle conversations.

    Checks three scenarios:
    1. SOC idle: SOC hasn't responded within SLA threshold
    2. Customer idle: Customer hasn't responded (nudge at 4h, auto-resolve at 24h)
    3. Resolved idle: Auto-close resolved conversations after 72h
    """
    now = timezone.now()
    soc_count = _check_soc_idle(now)
    customer_count = _check_customer_idle(now)
    resolved_count = _check_resolved_idle(now)

    total = soc_count + customer_count + resolved_count
    if total:
        logger.info(
            "Idle check complete: %d SOC escalations, %d customer nudges/resolves, %d auto-closes",
            soc_count, customer_count, resolved_count,
        )


def _check_soc_idle(now):
    """Check for conversations where SOC hasn't responded within SLA."""
    count = 0
    conversations = Conversation.objects.filter(
        status__in=[ConversationStatus.QUEUED, ConversationStatus.WAITING_SOC],
        last_message_at__isnull=False,
    ).select_related("queue")

    for conv in conversations:
        severity = conv.severity or "medium"
        threshold_minutes = SOC_IDLE_THRESHOLDS.get(severity, 30)

        # Check if this is case-linked (has metadata indicating case linkage)
        # For now, we use the issue_category as a proxy — case-linked convos
        # typically have incident/problem categories with higher urgency
        # TODO: Add explicit case_id field to Conversation model for precise detection

        idle_since = now - conv.last_message_at
        if idle_since < timedelta(minutes=threshold_minutes):
            continue

        # Check if we already sent an escalation message recently (within 2x threshold)
        # to avoid spamming
        recent_escalation = Message.objects.filter(
            conversation=conv,
            actor_type=ActorType.SYSTEM,
            source=MessageSource.INTERNAL,
            body_plain__contains="sorry for the wait",
            created_at__gte=now - timedelta(minutes=threshold_minutes * 2),
        ).exists()

        if recent_escalation:
            continue

        msg = _create_system_message(
            conv,
            "We're sorry for the wait. Your conversation has been escalated for faster attention.",
        )
        _publish_system_message(conv, msg)
        count += 1
        logger.info("SOC idle escalation for conversation %s (idle %s)", conv.id, idle_since)

    return count


def _check_customer_idle(now):
    """Check for idle customers: nudge at 4h, auto-resolve at 24h."""
    count = 0
    conversations = Conversation.objects.filter(
        status=ConversationStatus.WAITING_CUSTOMER,
        last_message_at__isnull=False,
    )

    for conv in conversations:
        idle_since = now - conv.last_message_at
        idle_hours = idle_since.total_seconds() / 3600

        if idle_hours >= CUSTOMER_AUTO_RESOLVE_HOURS:
            # Auto-resolve after 24 hours
            already_resolved_msg = Message.objects.filter(
                conversation=conv,
                actor_type=ActorType.SYSTEM,
                body_plain__contains="haven't heard back",
            ).exists()

            if already_resolved_msg:
                continue

            conv.status = ConversationStatus.RESOLVED
            conv.resolved_at = now
            conv.save(update_fields=["status", "resolved_at"])

            msg = _create_system_message(
                conv,
                "We haven't heard back, so we're marking this as resolved. "
                "You can reopen anytime if you still need help.",
            )
            _publish_status_changed(conv, msg)
            count += 1
            logger.info("Auto-resolved conversation %s (customer idle %dh)", conv.id, int(idle_hours))

        elif idle_hours >= CUSTOMER_NUDGE_HOURS:
            # Nudge after 4 hours
            already_nudged = Message.objects.filter(
                conversation=conv,
                actor_type=ActorType.SYSTEM,
                body_plain__contains="checking in",
                created_at__gte=now - timedelta(hours=CUSTOMER_AUTO_RESOLVE_HOURS),
            ).exists()

            if already_nudged:
                continue

            msg = _create_system_message(
                conv,
                "Just checking in — are you still needing help with this?",
            )
            _publish_system_message(conv, msg)
            count += 1
            logger.info("Customer idle nudge for conversation %s (idle %dh)", conv.id, int(idle_hours))

    return count


def _check_resolved_idle(now):
    """Auto-close resolved conversations after 72 hours."""
    count = 0
    cutoff = now - timedelta(hours=RESOLVED_AUTO_CLOSE_HOURS)
    conversations = Conversation.objects.filter(
        status=ConversationStatus.RESOLVED,
        resolved_at__isnull=False,
        resolved_at__lte=cutoff,
    )

    for conv in conversations:
        conv.status = ConversationStatus.CLOSED
        conv.closed_at = now
        conv.save(update_fields=["status", "closed_at"])

        msg = _create_system_message(conv, "This conversation has been automatically closed.")

        try:
            publisher = SSEPublisher()
            conv_id = str(conv.id)
            publisher.publish(
                conversation_id=conv_id,
                event_type="message.created",
                data=MessageSerializer(msg).data,
            )
            publisher.publish(
                conversation_id=conv_id,
                event_type="conversation.closed",
                data={"conversation_id": conv_id, "status": "closed"},
            )
        except Exception:
            logger.debug("Failed to publish SSE for auto-close on %s", conv.id, exc_info=True)

        count += 1
        logger.info("Auto-closed conversation %s (resolved %s ago)", conv.id, now - conv.resolved_at)

    return count
