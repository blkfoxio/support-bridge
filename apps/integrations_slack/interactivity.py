"""Handle Slack button clicks (Close it / I still need help) on resolved-conversation notices."""

import logging

import httpx

from apps.conversations.models import ConversationStatus
from apps.conversations.services import ConversationService

from .client import SlackClient
from .crypto import decrypt_token
from .inbound import SlackContext, _resolve_identity, _roam_client
from .models import InstallationStatus, SlackInstallation, SlackThread
from .outbound import ACTION_CLOSE, ACTION_REOPEN

logger = logging.getLogger(__name__)


def _replace_original(response_url: str, text: str) -> None:
    """Swap the buttons for a short note about who acted, so they can't be clicked twice."""
    if not response_url:
        return
    try:
        httpx.post(
            response_url,
            json={
                "replace_original": True,
                "text": text,
                "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
            },
            timeout=10,
        )
    except httpx.HTTPError:
        logger.exception("Failed to update Slack message via response_url")


def handle_interaction(payload: dict) -> None:
    if payload.get("type") != "block_actions":
        return
    action = (payload.get("actions") or [{}])[0]
    action_id, conversation_id = action.get("action_id"), action.get("value", "")
    if action_id not in (ACTION_CLOSE, ACTION_REOPEN):
        return

    team_id = (payload.get("team") or {}).get("id", "")
    user_id = (payload.get("user") or {}).get("id", "")
    install = SlackInstallation.objects.filter(team_id=team_id, status=InstallationStatus.ACTIVE).first()
    # The conversation must belong to this workspace; never trust the button value alone.
    thread = SlackThread.objects.select_related("conversation").filter(
        team_id=team_id, conversation_id=conversation_id
    ).first()
    if not install or not thread or not user_id:
        logger.warning("Ignoring Slack action %s for conversation %s from team %s", action_id, conversation_id, team_id)
        return

    from apps.organizations.services import ensure_organization

    ctx = SlackContext(
        install=install,
        org=ensure_organization(install.org_id, install.team_name),
        slack=SlackClient(decrypt_token(install.bot_token_encrypted)),
    )
    identity = _resolve_identity(ctx, user_id)
    if identity is None:
        return

    conversation = thread.conversation
    response_url = payload.get("response_url", "")
    if conversation.status != ConversationStatus.RESOLVED:
        _replace_original(response_url, f"This conversation is already {conversation.get_status_display().lower()}.")
        return

    service = ConversationService(_roam_client())
    # Anyone in the thread may act, so make sure they're a participant before the access-checked call.
    conversation.participants.get_or_create(user_id=identity.effective_user_id, defaults={"identity": identity})
    if action_id == ACTION_CLOSE:
        service.close_conversation(conversation_id=conversation.id, user_id=identity.effective_user_id,
                                   close_reason="Closed from Slack")
        _replace_original(response_url, f"✅ <@{user_id}> closed this conversation.")
    else:
        service.reopen_conversation(conversation_id=conversation.id, user_id=identity.effective_user_id)
        _replace_original(response_url, f"↩️ <@{user_id}> said they still need help.")
