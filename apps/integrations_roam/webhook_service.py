"""Webhook ingestion service for Roam chat events.

Processes inbound webhook payloads from Roam, creating Message rows for
analyst replies and publishing SSE events for real-time customer delivery.
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass

import requests as http_requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import EventLog
from apps.conversations.models import Conversation, ConversationStatus
from apps.customer_api.serializers import MessageSerializer
from apps.messaging.models import ActorType, Message, MessageDirection, MessageSource, MessageType
from apps.queues.models import AnalystProfile
from common.sse import SSEPublisher

logger = logging.getLogger(__name__)


@dataclass
class WebhookFields:
    """Extracted fields from a Roam webhook payload."""

    sender_id: str | None = None
    sender_name: str | None = None
    text: str | None = None
    thread_key: str | None = None
    chat_id: str | None = None
    message_id: str | None = None
    timestamp: int | None = None


def _extract_fields(payload: dict) -> WebhookFields:
    """Extract message fields from a Roam webhook payload.

    Tries multiple field name variants since Roam API is alpha and
    the exact webhook payload format is not fully documented.
    """
    return WebhookFields(
        sender_id=(
            payload.get("senderId")
            or payload.get("sender_id")
            or payload.get("sender")
            or payload.get("userId")
        ),
        sender_name=(
            payload.get("senderName")
            or payload.get("sender_name")
            or payload.get("name")
        ),
        text=(
            payload.get("text")
            or payload.get("message")
            or payload.get("body")
            or payload.get("content")
        ),
        thread_key=(
            payload.get("threadKey")
            or payload.get("thread_key")
            or payload.get("threadId")
        ),
        chat_id=(
            payload.get("chat")
            or payload.get("chatId")
            or payload.get("chat_id")
            or payload.get("group")
        ),
        message_id=(
            payload.get("id")
            or payload.get("messageId")
            or payload.get("message_id")
        ),
        timestamp=(
            payload.get("timestamp")
            or payload.get("ts")
        ),
    )


def _derive_idempotency_key(fields: WebhookFields, raw_payload: dict) -> str:
    """Derive a unique idempotency key for a webhook payload."""
    if fields.message_id:
        return f"roam:chat_message:{fields.message_id}"

    # Fallback: hash the payload with a timestamp bucket (1-second granularity)
    payload_hash = hashlib.sha256(json.dumps(raw_payload, sort_keys=True).encode()).hexdigest()[:16]
    ts_bucket = (fields.timestamp or 0) // 1000
    return f"roam:chat_message:{payload_hash}:{ts_bucket}"


def _send_push_notification(
    conversation_id: str,
    customer_cognito_sub: str,
    sender_name: str,
    message_preview: str,
) -> None:
    """Send a push notification to the customer's mobile device via Cloud Function."""
    push_url = getattr(settings, "PUSH_NOTIFICATION_URL", "")
    if not push_url:
        logger.debug("PUSH_NOTIFICATION_URL not configured, skipping push notification")
        return

    http_requests.post(
        push_url,
        json={
            "conversationId": conversation_id,
            "customerCognitoSub": customer_cognito_sub,
            "senderName": sender_name,
            "messagePreview": message_preview[:200],
        },
        timeout=5,
    )
    logger.info("Push notification sent for conversation %s", conversation_id)


def _is_bot_echo(sender_id: str) -> bool:
    """Check if a message is from a bot (our own echo or another bot)."""
    if not sender_id:
        return False

    # Roam bot IDs use the B- prefix
    if sender_id.startswith("B-"):
        return True

    # Check against our configured bot user ID
    bot_user_id = getattr(settings, "ROAM_BOT_USER_ID", "")
    if bot_user_id and sender_id == bot_user_id:
        return True

    return False


class WebhookService:
    """Processes inbound Roam webhook payloads."""

    def __init__(self):
        self._publisher = SSEPublisher()

    def handle_chat_message(self, raw_payload: dict) -> Message | None:
        """Process a chat-message webhook from Roam.

        Returns the created Message or None if the payload was ignored/duplicate.
        """
        # 1. Always persist the raw payload for debugging/replay
        raw_key = f"roam:raw:{uuid.uuid4().hex[:12]}"
        EventLog.objects.create(
            event_type="roam_webhook.chat_message.raw",
            idempotency_key=raw_key,
            source="roam_webhook",
            payload=raw_payload,
        )

        # 2. Extract fields adaptively
        fields = _extract_fields(raw_payload)

        if not fields.text or not fields.thread_key:
            logger.warning(
                "Webhook missing critical fields (text=%s, threadKey=%s), skipping",
                bool(fields.text),
                bool(fields.thread_key),
            )
            return None

        # 3. Derive idempotency key and check for duplicates
        idempotency_key = _derive_idempotency_key(fields, raw_payload)
        if EventLog.objects.filter(idempotency_key=idempotency_key).exists():
            logger.info("Duplicate webhook (idempotency_key=%s), skipping", idempotency_key)
            return None

        # 4. Bot echo detection
        if _is_bot_echo(fields.sender_id or ""):
            logger.info("Bot echo detected (sender=%s), skipping", fields.sender_id)
            return None

        # 5. Look up conversation by threadKey
        conversation = Conversation.objects.filter(roam_thread_key=fields.thread_key).first()
        if not conversation:
            logger.warning("No conversation found for threadKey=%s, storing as orphaned", fields.thread_key)
            EventLog.objects.create(
                event_type="roam_webhook.chat_message.orphaned",
                idempotency_key=f"roam:orphaned:{uuid.uuid4().hex[:12]}",
                source="roam_webhook",
                payload={
                    "thread_key": fields.thread_key,
                    "sender_id": fields.sender_id,
                    "text_preview": (fields.text or "")[:100],
                },
            )
            return None

        # 6. Resolve analyst identity
        analyst_profile = None
        actor_id = fields.sender_id or "unknown"
        sender_name = fields.sender_name or ""
        if fields.sender_id:
            analyst_profile = AnalystProfile.objects.filter(
                external_user_id=fields.sender_id
            ).first()
            if analyst_profile:
                actor_id = analyst_profile.external_user_id
                sender_name = sender_name or analyst_profile.display_name
            else:
                logger.info(
                    "No AnalystProfile for sender=%s, using raw ID. "
                    "Consider adding this analyst to the system.",
                    fields.sender_id,
                )

        # 7. Create message and update conversation atomically
        now = timezone.now()
        with transaction.atomic():
            message = Message.objects.create(
                conversation=conversation,
                actor_type=ActorType.ANALYST,
                actor_id=actor_id,
                direction=MessageDirection.OUTBOUND,
                source=MessageSource.ROAM_WEBHOOK,
                body_plain=fields.text,
                message_type=MessageType.TEXT,
                external_message_id=fields.message_id or "",
                delivered_at=now,
                metadata={
                    "roam_sender_id": fields.sender_id,
                    "roam_sender_name": sender_name,
                    "roam_chat_id": fields.chat_id,
                    "roam_timestamp": fields.timestamp,
                },
            )

            # Update conversation timestamps and status
            update_fields = ["last_message_at", "updated_at"]
            conversation.last_message_at = now

            if conversation.first_response_at is None:
                conversation.first_response_at = now
                update_fields.append("first_response_at")
                logger.info(
                    "First analyst response for conversation %s (SLA clock started)",
                    conversation.id,
                )

            if conversation.status in (ConversationStatus.QUEUED, ConversationStatus.WAITING_SOC):
                conversation.status = ConversationStatus.WAITING_CUSTOMER
                update_fields.append("status")

            conversation.save(update_fields=update_fields)

            # Record processed event
            EventLog.objects.create(
                event_type="roam_webhook.chat_message.processed",
                idempotency_key=idempotency_key,
                source="roam_webhook",
                conversation=conversation,
                payload={"message_id": str(message.id)},
                processed_at=now,
            )

        # 8. Publish SSE events (outside transaction)
        try:
            message_data = MessageSerializer(message).data
            self._publisher.publish(
                conversation_id=str(conversation.id),
                event_type="message.created",
                data=message_data,
            )
        except Exception:
            logger.exception("Failed to publish SSE event for message %s", message.id)

        # 9. Send push notification to customer's mobile device
        try:
            _send_push_notification(
                conversation_id=str(conversation.id),
                customer_cognito_sub=conversation.customer_user_id,
                sender_name=sender_name or "Cyflare Support",
                message_preview=(fields.text or "")[:200],
            )
        except Exception:
            logger.exception("Failed to send push notification for message %s", message.id)

        logger.info(
            "Processed analyst reply: conversation=%s message=%s sender=%s",
            conversation.id,
            message.id,
            fields.sender_id,
        )
        return message

    def handle_reaction(self, raw_payload: dict) -> None:
        """Process a reaction webhook from Roam.

        For the prototype, just persist the raw payload for later analysis.
        """
        EventLog.objects.create(
            event_type="roam_webhook.reaction.raw",
            idempotency_key=f"roam:reaction:{uuid.uuid4().hex[:12]}",
            source="roam_webhook",
            payload=raw_payload,
        )
        logger.info("Stored reaction webhook payload")
