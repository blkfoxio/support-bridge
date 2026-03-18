"""Fire-and-forget helpers for posting status notices to Roam threads."""

import logging

from asgiref.sync import async_to_sync
from django.conf import settings

from .formatters import format_system_note

logger = logging.getLogger(__name__)


def _make_client():
    """Create a fresh RoamClient (same pattern as integrations_roam.tasks)."""
    from .client import RoamClient

    return RoamClient(settings.ROAM_API_BASE_URL, settings.ROAM_API_TOKEN)


def post_status_to_roam(conversation, note: str) -> None:
    """Post a status notice to the Roam thread for a conversation.

    Best-effort: logs warnings on failure, never raises.
    """
    if not getattr(settings, "ROAM_API_TOKEN", ""):
        return

    from apps.queues.models import QueueGroupMapping

    mapping = QueueGroupMapping.objects.filter(
        queue=conversation.queue, active=True
    ).first()
    if not mapping:
        return

    try:
        client = _make_client()
        text = format_system_note(note=note)
        async_to_sync(client.post_message)(
            mapping.roam_group_id,
            text,
            thread_key=str(conversation.id),
        )
    except Exception:
        logger.warning(
            "Failed to post status to Roam for conversation %s",
            conversation.id,
            exc_info=True,
        )
