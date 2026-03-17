"""Conversation service — core business logic for conversation lifecycle."""

import logging
import uuid

from asgiref.sync import async_to_sync
from django.db import transaction
from django.utils import timezone

from apps.audit.models import EventLog
from apps.customer_api.serializers import MessageSerializer
from apps.integrations_roam.blocks import build_root_message_blocks
from apps.integrations_roam.formatters import format_customer_message
from apps.messaging.models import ActorType, Message, MessageDirection, MessageSource, MessageType
from apps.queues.models import QueueGroupMapping
from apps.routing.services import RoutingService
from common.sse import SSEPublisher

from .models import Conversation, ConversationStatus, SourceChannel

logger = logging.getLogger(__name__)


class ConversationService:
    """Handles conversation creation, messaging, and lifecycle transitions."""

    # Valid status transitions for lifecycle operations
    _RESOLVABLE_STATUSES = {
        ConversationStatus.ASSIGNED,
        ConversationStatus.WAITING_CUSTOMER,
        ConversationStatus.WAITING_SOC,
    }
    _CLOSEABLE_STATUSES = {
        ConversationStatus.RESOLVED,
        ConversationStatus.ASSIGNED,
        ConversationStatus.WAITING_CUSTOMER,
        ConversationStatus.WAITING_SOC,
    }
    _REOPENABLE_STATUSES = {
        ConversationStatus.RESOLVED,
        ConversationStatus.CLOSED,
    }

    def __init__(self, roam_client):
        self.roam_client = roam_client
        self.routing_service = RoutingService()

    def create_conversation(
        self,
        *,
        org_id: str,
        org_name: str,
        user_id: str,
        customer_name: str,
        customer_email: str,
        tier: str,
        issue_category: str,
        severity: str,
        source_channel: str,
        message_body: str,
        idempotency_key: str,
    ) -> tuple[Conversation, Message]:
        """Create a new conversation with initial message, route to queue, and post to Roam.

        Returns (conversation, message) tuple.
        Raises ValueError if idempotency_key was already processed (returns existing).
        """
        # 1. Idempotency check
        existing_event = EventLog.objects.filter(idempotency_key=idempotency_key).first()
        if existing_event and existing_event.conversation_id:
            conversation = Conversation.objects.get(id=existing_event.conversation_id)
            message = conversation.messages.first()
            logger.info("Duplicate create request (idempotency_key=%s), returning existing", idempotency_key)
            return conversation, message

        # 2. Route to queue
        target_queue = self.routing_service.evaluate(
            org_id=org_id, tier=tier, issue_category=issue_category, severity=severity
        )

        # 3. Get Roam group mapping
        group_mapping = QueueGroupMapping.objects.filter(queue=target_queue, active=True).first()
        roam_group_id = group_mapping.roam_group_id if group_mapping else None

        # 4. Create conversation and message atomically
        now = timezone.now()
        with transaction.atomic():
            conversation = Conversation.objects.create(
                customer_org_id=org_id,
                customer_org_name=org_name,
                customer_user_id=user_id,
                customer_name=customer_name,
                customer_email=customer_email,
                source_channel=source_channel,
                status=ConversationStatus.QUEUED,
                severity=severity,
                issue_category=issue_category,
                tier=tier,
                queue=target_queue,
                roam_thread_key=str(uuid.uuid4()),  # Will be set to conversation.id after save
                opened_at=now,
                last_message_at=now,
            )
            # Set roam_thread_key to conversation ID
            conversation.roam_thread_key = str(conversation.id)
            conversation.save(update_fields=["roam_thread_key"])

            message = Message.objects.create(
                conversation=conversation,
                actor_type=ActorType.CUSTOMER,
                actor_id=user_id,
                direction=MessageDirection.INBOUND,
                source=MessageSource.CUSTOMER_API,
                body_plain=message_body,
                message_type=MessageType.TEXT,
                metadata={"customer_name": customer_name},
            )

            # Record event
            EventLog.objects.create(
                event_type="conversation.created",
                idempotency_key=idempotency_key,
                source="customer_api",
                conversation=conversation,
                payload={
                    "org_id": org_id,
                    "user_id": user_id,
                    "queue_key": target_queue.key,
                    "severity": severity,
                },
            )

        # 5. Post to Roam (outside transaction — Roam failure shouldn't roll back DB)
        if roam_group_id:
            try:
                blocks, color = build_root_message_blocks(
                    customer_name=customer_name,
                    customer_email=customer_email,
                    org_name=org_name,
                    org_id=org_id,
                    tier=tier,
                    severity=severity,
                    issue_category=issue_category,
                    queue_name=target_queue.name,
                    conversation_id=str(conversation.id),
                    message_body=message_body,
                )
                roam_response = async_to_sync(self.roam_client.post_blocks)(
                    roam_group_id, blocks, color=color, thread_key=str(conversation.id)
                )
                # Store external metadata
                message.external_message_id = str(roam_response.timestamp or "")
                message.delivered_at = timezone.now()
                message.save(update_fields=["external_message_id", "delivered_at"])

                # Save the root message timestamp for polling thread replies.
                # For root messages, chat.post returns the message timestamp
                # (not threadTimestamp, which is None for root messages).
                # This timestamp IS the threadTimestamp for fetching replies.
                thread_ts = roam_response.thread_timestamp or roam_response.timestamp
                if thread_ts:
                    conversation.roam_thread_timestamp = thread_ts
                    conversation.save(update_fields=["roam_thread_timestamp"])

                logger.info("Posted to Roam group=%s thread_key=%s", roam_group_id, conversation.id)
            except Exception:
                message.failed_at = timezone.now()
                message.save(update_fields=["failed_at"])
                logger.exception("Failed to post to Roam for conversation %s", conversation.id)
        else:
            logger.warning("No active Roam group mapping for queue '%s'", target_queue.key)

        return conversation, message

    def send_message(
        self,
        *,
        conversation_id: str,
        user_id: str,
        body: str,
        idempotency_key: str,
    ) -> Message:
        """Send a customer message to an existing conversation.

        Validates ownership, creates the message, and posts to Roam.
        """
        # 1. Get and validate conversation
        conversation = Conversation.objects.select_related("queue").get(id=conversation_id)
        if conversation.customer_user_id != user_id:
            raise PermissionError("User does not own this conversation")

        if conversation.status == ConversationStatus.CLOSED:
            raise ValueError("Cannot send messages to a closed conversation")

        # 2. Idempotency check
        existing_event = EventLog.objects.filter(idempotency_key=idempotency_key).first()
        if existing_event:
            return Message.objects.filter(
                conversation=conversation,
                actor_id=user_id,
            ).order_by("-created_at").first()

        # 3. Create message
        now = timezone.now()
        message = Message.objects.create(
            conversation=conversation,
            actor_type=ActorType.CUSTOMER,
            actor_id=user_id,
            direction=MessageDirection.INBOUND,
            source=MessageSource.CUSTOMER_API,
            body_plain=body,
            message_type=MessageType.TEXT,
            metadata={"customer_name": conversation.customer_name},
        )

        # 4. Update conversation
        conversation.last_message_at = now
        update_fields = ["last_message_at"]
        if conversation.status in (ConversationStatus.WAITING_CUSTOMER, ConversationStatus.RESOLVED):
            # Auto-reopen resolved conversations when customer sends a message
            conversation.status = ConversationStatus.WAITING_SOC
            update_fields.append("status")
        conversation.save(update_fields=update_fields)

        # 5. Record event
        EventLog.objects.create(
            event_type="message.sent",
            idempotency_key=idempotency_key,
            source="customer_api",
            conversation=conversation,
            payload={"message_id": str(message.id)},
        )

        # 6. Post to Roam
        group_mapping = QueueGroupMapping.objects.filter(queue=conversation.queue, active=True).first()
        if group_mapping:
            try:
                roam_text = format_customer_message(
                    customer_name=conversation.customer_name,
                    org_name=conversation.customer_org_name,
                    message_body=body,
                )
                roam_response = async_to_sync(self.roam_client.post_message)(
                    group_mapping.roam_group_id, roam_text, thread_key=str(conversation.id)
                )
                message.external_message_id = str(roam_response.timestamp or "")
                message.delivered_at = timezone.now()
                message.save(update_fields=["external_message_id", "delivered_at"])
            except Exception:
                message.failed_at = timezone.now()
                message.save(update_fields=["failed_at"])
                logger.exception("Failed to post message to Roam for conversation %s", conversation.id)

        # 7. Publish SSE event for real-time delivery
        try:
            SSEPublisher().publish(
                conversation_id=str(conversation.id),
                event_type="message.created",
                data=MessageSerializer(message).data,
            )
        except Exception:
            logger.debug("Failed to publish SSE event for message %s", message.id, exc_info=True)

        return message

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def _create_system_message(self, conversation: Conversation, body: str) -> Message:
        """Create an internal system message (not posted to Roam)."""
        return Message.objects.create(
            conversation=conversation,
            actor_type=ActorType.SYSTEM,
            actor_id="system",
            direction=MessageDirection.OUTBOUND,
            source=MessageSource.INTERNAL,
            body_plain=body,
            message_type=MessageType.SYSTEM_NOTE,
        )

    def _publish_status_changed(self, conversation: Conversation, system_message: Message) -> None:
        """Publish SSE events for a status transition + the system message."""
        publisher = SSEPublisher()
        conv_id = str(conversation.id)

        # Publish the system message so the customer sees it in the thread
        publisher.publish(
            conversation_id=conv_id,
            event_type="message.created",
            data=MessageSerializer(system_message).data,
        )

        # Publish the status change so the client can update UI state
        publisher.publish(
            conversation_id=conv_id,
            event_type="conversation.status_changed",
            data={"conversation_id": conv_id, "status": conversation.status},
        )

    def resolve_conversation(
        self,
        *,
        conversation_id: str,
        actor_id: str,
        resolution_note: str = "",
    ) -> Conversation:
        """Mark a conversation as resolved (soft close).

        Typically triggered by an analyst. The customer can confirm (close) or reopen.
        """
        conversation = Conversation.objects.get(id=conversation_id)

        if conversation.status not in self._RESOLVABLE_STATUSES:
            raise ValueError(
                f"Cannot resolve conversation in '{conversation.status}' status. "
                f"Must be one of: {', '.join(s.value for s in self._RESOLVABLE_STATUSES)}"
            )

        now = timezone.now()
        conversation.status = ConversationStatus.RESOLVED
        conversation.resolved_at = now
        conversation.save(update_fields=["status", "resolved_at"])

        body = "Your analyst has resolved this conversation. If you still need help, you can reopen it."
        if resolution_note:
            body = f"{body}\n\nNote: {resolution_note}"
        system_msg = self._create_system_message(conversation, body)

        EventLog.objects.create(
            event_type="conversation.resolved",
            idempotency_key=f"resolve-{conversation_id}-{now.isoformat()}",
            source="ops_api",
            conversation=conversation,
            payload={"actor_id": actor_id, "resolution_note": resolution_note},
        )

        try:
            self._publish_status_changed(conversation, system_msg)
        except Exception:
            logger.debug("Failed to publish SSE for resolve on %s", conversation_id, exc_info=True)

        logger.info("Conversation %s resolved by %s", conversation_id, actor_id)
        return conversation

    def close_conversation(
        self,
        *,
        conversation_id: str,
        user_id: str,
        close_reason: str = "",
    ) -> Conversation:
        """Close a conversation (hard close).

        Typically triggered by the customer confirming resolution, or proactively ending.
        """
        conversation = Conversation.objects.get(id=conversation_id)
        if conversation.customer_user_id != user_id:
            raise PermissionError("User does not own this conversation")

        if conversation.status not in self._CLOSEABLE_STATUSES:
            raise ValueError(
                f"Cannot close conversation in '{conversation.status}' status. "
                f"Must be one of: {', '.join(s.value for s in self._CLOSEABLE_STATUSES)}"
            )

        now = timezone.now()
        conversation.status = ConversationStatus.CLOSED
        conversation.closed_at = now
        conversation.save(update_fields=["status", "closed_at"])

        system_msg = self._create_system_message(conversation, "This conversation has been closed.")

        EventLog.objects.create(
            event_type="conversation.closed",
            idempotency_key=f"close-{conversation_id}-{now.isoformat()}",
            source="customer_api",
            conversation=conversation,
            payload={"user_id": user_id, "close_reason": close_reason},
        )

        try:
            publisher = SSEPublisher()
            conv_id = str(conversation.id)
            # Publish system message
            publisher.publish(
                conversation_id=conv_id,
                event_type="message.created",
                data=MessageSerializer(system_msg).data,
            )
            # Publish conversation.closed — clients should disconnect SSE on this event
            publisher.publish(
                conversation_id=conv_id,
                event_type="conversation.closed",
                data={"conversation_id": conv_id, "status": "closed"},
            )
        except Exception:
            logger.debug("Failed to publish SSE for close on %s", conversation_id, exc_info=True)

        logger.info("Conversation %s closed by customer %s", conversation_id, user_id)
        return conversation

    def reopen_conversation(
        self,
        *,
        conversation_id: str,
        user_id: str,
    ) -> Conversation:
        """Reopen a resolved or closed conversation.

        Transitions back to waiting_soc so the SOC team knows the customer needs more help.
        """
        conversation = Conversation.objects.get(id=conversation_id)
        if conversation.customer_user_id != user_id:
            raise PermissionError("User does not own this conversation")

        if conversation.status not in self._REOPENABLE_STATUSES:
            raise ValueError(
                f"Cannot reopen conversation in '{conversation.status}' status. "
                f"Must be one of: {', '.join(s.value for s in self._REOPENABLE_STATUSES)}"
            )

        now = timezone.now()
        conversation.status = ConversationStatus.WAITING_SOC
        conversation.last_message_at = now
        # Clear closed_at if reopening from closed
        if conversation.closed_at:
            conversation.closed_at = None
        conversation.save(update_fields=["status", "last_message_at", "closed_at"])

        system_msg = self._create_system_message(conversation, "You reopened this conversation.")

        EventLog.objects.create(
            event_type="conversation.reopened",
            idempotency_key=f"reopen-{conversation_id}-{now.isoformat()}",
            source="customer_api",
            conversation=conversation,
            payload={"user_id": user_id},
        )

        try:
            self._publish_status_changed(conversation, system_msg)
        except Exception:
            logger.debug("Failed to publish SSE for reopen on %s", conversation_id, exc_info=True)

        logger.info("Conversation %s reopened by customer %s", conversation_id, user_id)
        return conversation
