"""Celery tasks for Roam integration — polling for analyst replies.

Since Roam doesn't support outbound webhooks for chat messages,
we poll chat.history on a schedule to pick up analyst replies and
feed them through the existing WebhookService pipeline.
"""

import logging

from asgiref.sync import async_to_sync
from celery import shared_task
from django.conf import settings

from apps.conversations.models import Conversation, ConversationStatus

logger = logging.getLogger(__name__)

# Statuses where we expect analyst replies
_ACTIVE_STATUSES = [
    ConversationStatus.QUEUED,
    ConversationStatus.ASSIGNED,
    ConversationStatus.WAITING_SOC,
    ConversationStatus.WAITING_CUSTOMER,
]


def _make_client():
    """Create a fresh RoamClient.

    A new instance is needed per async_to_sync call group because httpx
    AsyncClient connection pools are bound to the event loop they first
    run in.  Each async_to_sync invocation spins up its own loop, so
    reusing a client across calls causes 'Event loop is closed' errors.
    """
    from apps.integrations_roam.client import RoamClient

    return RoamClient(settings.ROAM_API_BASE_URL, settings.ROAM_API_TOKEN)


def _fetch_user_names():
    """Fetch Roam user ID → display name mapping."""
    try:
        client = _make_client()
        users = async_to_sync(client.list_users)()
        return {u.id: u.name for u in users if u.name}
    except Exception:
        logger.warning("Could not fetch Roam user list for name resolution", exc_info=True)
        return {}


@shared_task(name="roam.poll_replies", bind=True, max_retries=0)
def poll_roam_replies(self):
    """Poll Roam chat.history for new analyst replies on active conversations.

    For each active conversation with a roam_thread_timestamp:
    1. Fetch thread replies from Roam
    2. Skip messages we've already processed (by external_message_id)
    3. Feed new messages through WebhookService.handle_chat_message()
    """
    from apps.integrations_roam.webhook_service import WebhookService

    if not settings.ROAM_API_TOKEN:
        logger.debug("ROAM_API_TOKEN not set, skipping poll")
        return

    # Find active conversations that have Roam threads
    conversations = Conversation.objects.filter(
        status__in=_ACTIVE_STATUSES,
        roam_thread_timestamp__isnull=False,
    ).select_related("queue")

    if not conversations.exists():
        return

    webhook_service = WebhookService()
    user_names = _fetch_user_names()
    total_new = 0

    for conv in conversations:
        try:
            total_new += _poll_conversation(webhook_service, conv, user_names)
        except Exception:
            logger.exception("Failed to poll Roam for conversation %s", conv.id)

    if total_new:
        logger.info("Roam poll complete: %d new messages across %d conversations", total_new, conversations.count())


def _poll_conversation(webhook_service, conv, user_names=None):
    """Poll a single conversation's Roam thread for new messages.

    Creates a fresh RoamClient per conversation to avoid httpx connection
    pool issues across async_to_sync event loop boundaries.

    Returns the number of new messages processed.
    """
    from apps.messaging.models import Message
    from apps.queues.models import QueueGroupMapping

    # Get the Roam group ID for this conversation's queue
    mapping = QueueGroupMapping.objects.filter(
        queue=conv.queue, active=True
    ).first()
    if not mapping:
        return 0

    # Fetch thread replies from Roam (fresh client per call)
    client = _make_client()
    messages = async_to_sync(client.get_chat_history)(
        mapping.roam_group_id,
        thread_timestamp=conv.roam_thread_timestamp,
        limit=50,
    )

    if not messages:
        return 0

    # Get external_message_ids we've already processed
    existing_ids = set(
        Message.objects.filter(
            conversation=conv,
            external_message_id__in=[str(m.timestamp) for m in messages if m.timestamp],
        ).values_list("external_message_id", flat=True)
    )

    new_count = 0
    for roam_msg in messages:
        msg_id = str(roam_msg.timestamp or roam_msg.id)

        # Skip messages we've already ingested
        if msg_id in existing_ids:
            continue

        # Resolve sender name from Roam user list or message data
        sender_name = roam_msg.sender_name
        if not sender_name and user_names and roam_msg.sender_id:
            sender_name = user_names.get(roam_msg.sender_id, "")

        # Build a webhook-like payload and feed through the existing pipeline
        payload = {
            "senderId": roam_msg.sender_id,
            "senderName": sender_name,
            "text": roam_msg.text,
            "threadKey": str(conv.roam_thread_key),
            "chat": mapping.roam_group_id,
            "id": roam_msg.id or msg_id,
            "timestamp": roam_msg.timestamp,
        }

        result = webhook_service.handle_chat_message(payload)
        if result is not None:
            new_count += 1

    return new_count
