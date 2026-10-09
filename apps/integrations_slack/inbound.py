"""Turn Slack events into conversations and customer messages.

Called from a Celery task so the Events API endpoint can acknowledge within Slack's 3-second limit.
"""

import fnmatch
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import EventLog
from apps.conversations.models import Conversation, ConversationParticipant, ConversationStatus, SourceChannel
from apps.conversations.services import ConversationService
from apps.identities.models import ExternalIdentity, IdentityProvider
from apps.identities.services import upsert_identity
from apps.integrations_roam.client import RoamClient
from apps.integrations_roam.mock_client import MockRoamClient
from apps.messaging.models import MessageSource
from apps.organizations.models import Organization, SlackConversationTrigger
from apps.organizations.services import ensure_organization

from .client import SlackClient
from .crypto import decrypt_token
from .models import InstallationStatus, SlackChannel, SlackInstallation, SlackThread

logger = logging.getLogger(__name__)

# Message subtypes that carry a real customer message; everything else (edits, joins, bot posts) is ignored.
_ACCEPTED_SUBTYPES = {None, "thread_broadcast", "file_share"}
_CLOSED = (ConversationStatus.CLOSED,)
_NOT_OPEN = (ConversationStatus.RESOLVED, ConversationStatus.CLOSED)

ACK_NEW = "Thanks, a Cyflare analyst will reply here. Please keep the conversation in this thread."
ACK_NEW_DM = "Thanks, a Cyflare analyst will reply here."
ACK_REOPENED = "That conversation was closed, so I've started a new one. A Cyflare analyst will reply here."
NOTICE_UNLINKED = (
    "To chat with Cyflare from Slack, your Slack account needs to be linked to a Cyflare ONE account. "
    "Ask your Cyflare ONE admin, or contact Cyflare support."
)
NOTICE_PENDING = (
    "This workspace hasn't been connected to Cyflare ONE yet. "
    "A Cyflare ONE user in your organization needs to finish setup before I can pass messages to the SOC."
)


def _roam_client():
    if settings.ROAM_API_TOKEN:
        return RoamClient(settings.ROAM_API_BASE_URL, settings.ROAM_API_TOKEN)
    return MockRoamClient()


@dataclass
class SlackContext:
    install: SlackInstallation
    org: Organization
    slack: SlackClient


def handle_event(payload: dict) -> None:
    """Process one Events API ``event_callback`` payload (deduplicated on Slack's event_id)."""
    event = payload.get("event") or {}
    team_id = payload.get("team_id", "")
    event_id = payload.get("event_id") or f"{team_id}:{event.get('event_ts', '')}"
    try:
        with transaction.atomic():
            EventLog.objects.create(
                event_type=f"slack.{event.get('type', 'unknown')}",
                idempotency_key=f"slack:event:{event_id}",
                source="slack",
                payload=payload,
                processed_at=timezone.now(),
            )
    except IntegrityError:
        logger.info("Duplicate Slack event %s, skipping", event_id)
        return

    from .services import deactivate_installation

    event_type = event.get("type")
    if event_type in ("app_uninstalled", "tokens_revoked"):
        deactivate_installation(team_id, reason=event_type)
        return

    install = SlackInstallation.objects.filter(team_id=team_id).first()
    if not install or install.status == InstallationStatus.INACTIVE:
        return
    slack = SlackClient(decrypt_token(install.bot_token_encrypted))
    if install.status == InstallationStatus.PENDING:
        if event_type == "message" and _is_customer_message(install, event):
            _notify_once(slack, f"slack_pending:{team_id}:{event['channel']}", event["channel"], NOTICE_PENDING,
                         thread_ts=event.get("thread_ts") or event.get("ts"))
        return

    ctx = SlackContext(install=install, org=ensure_organization(install.org_id, install.team_name), slack=slack)
    handlers = {
        "message": _handle_message,
        "reaction_added": _handle_reaction,
        "member_joined_channel": _handle_member_joined,
        "channel_created": _handle_channel_created_or_renamed,
        "channel_rename": _handle_channel_created_or_renamed,
    }
    handler = handlers.get(event_type)
    if handler:
        handler(ctx, event)


# --- Messages -------------------------------------------------------------


def _is_customer_message(install: SlackInstallation, event: dict) -> bool:
    if event.get("bot_id") or event.get("hidden") or not event.get("user"):
        return False
    if event.get("subtype") not in _ACCEPTED_SUBTYPES:
        return False
    if event.get("user") == install.bot_user_id:
        return False
    if event.get("channel_type") == "mpim":
        return False
    # Slack Connect: ignore people from other workspaces sharing the channel.
    user_team = event.get("user_team") or event.get("team")
    return not (user_team and user_team != install.team_id)


def _message_text(event: dict) -> str:
    text = (event.get("text") or "").strip()
    files = event.get("files") or []
    if files:
        note = f"📎 {len(files)} file(s) attached, view in Slack"
        text = f"{text}\n\n{note}" if text else note
    return text


def _handle_message(ctx: SlackContext, event: dict) -> None:
    if not _is_customer_message(ctx.install, event):
        return
    text = _message_text(event)
    if not text:
        return

    channel_id = event["channel"]
    is_im = event.get("channel_type") == "im"
    channel = _ensure_channel(ctx, channel_id, is_im=is_im)
    if not channel.enabled:
        return

    ts = event["ts"]
    thread_ts = event.get("thread_ts")
    identity = _resolve_identity(ctx, event["user"])
    if identity is None:
        return

    if is_im:
        thread = _latest_thread(ctx, channel_id, "")
        if thread and thread.conversation.status not in _CLOSED:
            _append(ctx, thread.conversation, identity, text, channel_id, ts)
        else:
            _start(ctx, identity, text, channel_id, ts, map_thread_ts="", reply_thread_ts=None, ack=ACK_NEW_DM)
        return

    if thread_ts and thread_ts != ts:
        thread = _latest_thread(ctx, channel_id, thread_ts)
        if not thread:
            return  # a thread the bot isn't tracking
        if thread.conversation.status in _CLOSED:
            _start(ctx, identity, text, channel_id, ts, map_thread_ts=thread_ts, reply_thread_ts=thread_ts,
                   ack=ACK_REOPENED, previous=thread.conversation)
        else:
            _append(ctx, thread.conversation, identity, text, channel_id, ts)
        return

    if _effective_trigger(ctx, channel) == SlackConversationTrigger.EMOJI:
        return
    merge_into = _merge_candidate(ctx, channel_id, identity)
    if merge_into:
        if _append(ctx, merge_into, identity, text, channel_id, ts):
            SlackThread.objects.create(conversation=merge_into, team_id=ctx.install.team_id,
                                       channel_id=channel_id, thread_ts=ts)
        return
    _start(ctx, identity, text, channel_id, ts, map_thread_ts=ts, reply_thread_ts=ts, ack=ACK_NEW)


def _handle_reaction(ctx: SlackContext, event: dict) -> None:
    item = event.get("item") or {}
    if item.get("type") != "message" or event.get("reaction") != ctx.org.slack_trigger_emoji:
        return
    channel_id, ts = item.get("channel", ""), item.get("ts", "")
    channel = _ensure_channel(ctx, channel_id, is_im=channel_id.startswith("D"))
    if not channel.enabled or channel.is_im or _effective_trigger(ctx, channel) != SlackConversationTrigger.EMOJI:
        return
    if _latest_thread(ctx, channel_id, ts):
        return  # already a conversation
    message = ctx.slack.get_message(channel_id, ts)
    if not message or message.get("thread_ts") not in (None, ts):
        return  # only top-level messages can start a conversation
    message = {**message, "channel": channel_id, "channel_type": "channel"}
    if not _is_customer_message(ctx.install, message):
        return
    identity = _resolve_identity(ctx, message["user"])
    text = _message_text(message)
    if identity and text:
        _start(ctx, identity, text, channel_id, ts, map_thread_ts=ts, reply_thread_ts=ts, ack=ACK_NEW)


def _effective_trigger(ctx: SlackContext, channel: SlackChannel) -> str:
    return channel.conversation_trigger or ctx.org.slack_conversation_trigger


def _latest_thread(ctx: SlackContext, channel_id: str, thread_ts: str) -> SlackThread | None:
    return (
        SlackThread.objects.select_related("conversation")
        .filter(team_id=ctx.install.team_id, channel_id=channel_id, thread_ts=thread_ts)
        .first()
    )


def _merge_candidate(ctx: SlackContext, channel_id: str, identity: ExternalIdentity) -> Conversation | None:
    since = timezone.now() - timedelta(minutes=ctx.org.slack_merge_window_minutes)
    thread = (
        SlackThread.objects.select_related("conversation")
        .filter(
            team_id=ctx.install.team_id,
            channel_id=channel_id,
            conversation__participants__user_id=identity.effective_user_id,
            conversation__last_message_at__gte=since,
        )
        .exclude(thread_ts="")
        .exclude(conversation__status__in=_NOT_OPEN)
        .first()
    )
    return thread.conversation if thread else None


def _allowed(ctx: SlackContext, identity: ExternalIdentity, channel_id: str, thread_ts: str | None) -> bool:
    if ctx.org.slack_allow_unlinked_users or identity.linked_user_id:
        return True
    _notify_once(ctx.slack, f"slack_unlinked:{identity.pk}", channel_id, NOTICE_UNLINKED, thread_ts=thread_ts)
    return False


def _start(ctx, identity, text, channel_id, ts, *, map_thread_ts, reply_thread_ts, ack, previous=None):
    if not _allowed(ctx, identity, channel_id, reply_thread_ts):
        return None
    metadata = {"slack_ts": ts, "slack_channel": channel_id, "slack_user": identity.external_user_id}
    if previous:
        metadata["previous_conversation_id"] = str(previous.id)
    conversation, _ = ConversationService(_roam_client()).create_conversation(
        org_id=ctx.install.org_id,
        org_name=ctx.org.name or ctx.install.team_name,
        user_id=identity.effective_user_id,
        customer_name=identity.display_name or "Slack user",
        customer_email=identity.email,
        tier="standard",
        issue_category="general",
        severity="medium",
        source_channel=SourceChannel.SLACK,
        message_body=text,
        idempotency_key=f"slack:msg:{ctx.install.team_id}:{channel_id}:{ts}",
        message_source=MessageSource.SLACK,
        message_metadata=metadata,
        channel_label="Slack",
    )
    ConversationParticipant.objects.filter(conversation=conversation, user_id=identity.effective_user_id).update(
        identity=identity
    )
    thread, created = SlackThread.objects.get_or_create(
        conversation=conversation, team_id=ctx.install.team_id, channel_id=channel_id, thread_ts=map_thread_ts
    )
    if created:
        _post(ctx.slack, channel_id, ack, thread_ts=reply_thread_ts)
    return conversation


def _append(ctx, conversation, identity, text, channel_id, ts) -> bool:
    if not _allowed(ctx, identity, channel_id, None):
        return False
    ConversationService(_roam_client()).append_external_message(
        conversation,
        user_id=identity.effective_user_id,
        sender_name=identity.display_name or "Slack user",
        body=text,
        idempotency_key=f"slack:msg:{ctx.install.team_id}:{channel_id}:{ts}",
        source=MessageSource.SLACK,
        metadata={"slack_ts": ts, "slack_channel": channel_id, "slack_user": identity.external_user_id},
    )
    ConversationParticipant.objects.filter(
        conversation=conversation, user_id=identity.effective_user_id, identity__isnull=True
    ).update(identity=identity)
    return True


# --- Identities and channels ----------------------------------------------


def _resolve_identity(ctx: SlackContext, user_id: str) -> ExternalIdentity | None:
    cache_key = f"slack_user:{ctx.install.team_id}:{user_id}"
    profile = cache.get(cache_key)
    if profile is None:
        try:
            user = ctx.slack.user_info(user_id)
        except Exception:
            logger.exception("users.info failed for %s in %s", user_id, ctx.install.team_id)
            user = {"id": user_id}
        p = user.get("profile") or {}
        profile = {
            "is_bot": bool(user.get("is_bot")),
            "email": p.get("email", ""),
            "name": p.get("display_name") or p.get("real_name") or user.get("real_name") or user.get("name", ""),
        }
        cache.set(cache_key, profile, 3600)
    if profile["is_bot"]:
        return None
    return upsert_identity(
        provider=IdentityProvider.SLACK,
        team_id=ctx.install.team_id,
        external_user_id=user_id,
        org_id=ctx.install.org_id,
        email=profile["email"],
        display_name=profile["name"],
    )


def _ensure_channel(ctx: SlackContext, channel_id: str, *, is_im: bool) -> SlackChannel:
    channel = SlackChannel.objects.filter(installation=ctx.install, channel_id=channel_id).first()
    if channel:
        return channel
    name, is_private = "", False
    if not is_im:
        try:
            info = ctx.slack.conversation_info(channel_id)
            name, is_private = info.get("name", ""), bool(info.get("is_private"))
        except Exception:
            logger.exception("conversations.info failed for %s", channel_id)
    channel, _ = SlackChannel.objects.get_or_create(
        installation=ctx.install,
        channel_id=channel_id,
        defaults={"name": name, "is_private": is_private, "is_im": is_im},
    )
    return channel


def _handle_member_joined(ctx: SlackContext, event: dict) -> None:
    if event.get("user") == ctx.install.bot_user_id:
        _ensure_channel(ctx, event.get("channel", ""), is_im=False)


def _handle_channel_created_or_renamed(ctx: SlackContext, event: dict) -> None:
    info = event.get("channel") or {}
    pattern = ctx.org.slack_auto_join_pattern
    channel_id, name = info.get("id", ""), info.get("name", "")
    if not pattern or not channel_id or not fnmatch.fnmatch(name, pattern):
        return
    try:
        ctx.slack.join_channel(channel_id)
    except Exception:
        logger.exception("Auto-join failed for #%s (%s)", name, channel_id)
        return
    channel, created = SlackChannel.objects.get_or_create(
        installation=ctx.install, channel_id=channel_id, defaults={"name": name}
    )
    if not created and channel.name != name:
        channel.name = name
        channel.save(update_fields=["name", "updated_at"])


# --- Posting helpers --------------------------------------------------------


def _post(slack: SlackClient, channel: str, text: str, *, thread_ts: str | None = None) -> None:
    try:
        slack.post_message(channel, text, thread_ts=thread_ts)
    except Exception:
        logger.exception("Failed to post notice to Slack channel %s", channel)


def _notify_once(slack: SlackClient, key: str, channel: str, text: str, *, thread_ts: str | None = None) -> None:
    """Post a notice at most once per hour per key, so repeated messages don't spam the channel."""
    if cache.add(key, 1, 3600):
        _post(slack, channel, text, thread_ts=thread_ts)
