"""Conversation service — core business logic for conversation lifecycle."""

import logging
import uuid

from asgiref.sync import async_to_sync
from django.db import transaction
from django.utils import timezone

from apps.audit.models import EventLog
from apps.integrations_roam.formatters import format_customer_message, format_root_message
from apps.messaging.models import ActorType, Message, MessageDirection, MessageSource, MessageType
from apps.queues.models import QueueGroupMapping
from apps.routing.services import RoutingService

from .models import Conversation, ConversationStatus, SourceChannel

logger = logging.getLogger(__name__)


class ConversationService:
    """Handles conversation creation and message sending."""

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
                roam_text = format_root_message(
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
                roam_response = async_to_sync(self.roam_client.post_message)(
                    roam_group_id, roam_text, thread_key=str(conversation.id)
                )
                # Store external metadata
                message.external_message_id = str(roam_response.timestamp or "")
                message.delivered_at = timezone.now()
                message.save(update_fields=["external_message_id", "delivered_at"])
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
        )

        # 4. Update conversation
        conversation.last_message_at = now
        update_fields = ["last_message_at"]
        if conversation.status == ConversationStatus.WAITING_CUSTOMER:
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

        return message
