"""Customer-side delivery of outbound messages.

Every outbound message goes out over SSE (web widget / open apps) and mobile
push. External customer channels such as Slack register a ``ChannelDeliverer``
so the same message is also posted where the conversation started.
"""

import logging
from typing import Protocol

import requests as http_requests
from django.conf import settings

from apps.conversations.models import Conversation
from apps.customer_api.serializers import MessageSerializer
from common.sse import SSEPublisher

from .models import Message

logger = logging.getLogger(__name__)


class ChannelDeliverer(Protocol):
    """An external customer channel (e.g. Slack) that mirrors outbound messages."""

    name: str

    def applies_to(self, conversation: Conversation) -> bool: ...

    def deliver_message(self, conversation: Conversation, message: Message, sender_name: str) -> None: ...


_channel_deliverers: list[ChannelDeliverer] = []


def register_channel_deliverer(deliverer: ChannelDeliverer) -> None:
    """Register an external channel; called from the integration app's ``AppConfig.ready``."""
    if all(d.name != deliverer.name for d in _channel_deliverers):
        _channel_deliverers.append(deliverer)


def send_push_notification(
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


class CustomerDeliveryDispatcher:
    """Fans an outbound message out to every customer-side channel. Failures are logged, never raised."""

    def __init__(self, publisher: SSEPublisher | None = None):
        self._publisher = publisher or SSEPublisher()

    def deliver_message(self, conversation: Conversation, message: Message, sender_name: str) -> None:
        try:
            self._publisher.publish(
                conversation_id=str(conversation.id),
                event_type="message.created",
                data=MessageSerializer(message).data,
            )
        except Exception:
            logger.exception("Failed to publish SSE event for message %s", message.id)

        try:
            send_push_notification(
                conversation_id=str(conversation.id),
                customer_cognito_sub=conversation.customer_user_id,
                sender_name=sender_name,
                message_preview=message.body_plain[:200],
            )
        except Exception:
            logger.exception("Failed to send push notification for message %s", message.id)

        self.deliver_to_external_channels(conversation, message, sender_name)

    def deliver_to_external_channels(self, conversation: Conversation, message: Message, sender_name: str) -> None:
        """Mirror a message into external channels (e.g. the Slack thread) without SSE or push."""
        for deliverer in _channel_deliverers:
            try:
                if deliverer.applies_to(conversation):
                    deliverer.deliver_message(conversation, message, sender_name)
            except Exception:
                logger.exception("Failed to deliver message %s via %s", message.id, deliverer.name)
