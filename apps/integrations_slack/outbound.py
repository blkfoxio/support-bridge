"""Post outbound messages (analyst replies, messages sent from the Cyflare app) into the Slack thread."""

import logging

from apps.conversations.models import Conversation, ConversationStatus
from apps.messaging.models import ActorType, Message, MessageSource

from .client import SlackClient
from .crypto import decrypt_token
from .models import InstallationStatus, SlackInstallation, SlackThread

logger = logging.getLogger(__name__)


class SlackDeliverer:
    """Registered with the customer delivery dispatcher; queues a Slack post for Slack-linked conversations."""

    name = "slack"

    def applies_to(self, conversation: Conversation) -> bool:
        return SlackThread.objects.filter(conversation=conversation).exists()

    def deliver_message(self, conversation: Conversation, message: Message, sender_name: str) -> None:
        if message.source == MessageSource.SLACK:
            return  # it came from Slack; don't echo it back
        from .tasks import deliver_to_slack

        deliver_to_slack.delay(str(message.id), sender_name)

    def deliver_system_message(self, conversation: Conversation, message: Message) -> None:
        from .tasks import deliver_status_to_slack

        deliver_status_to_slack.delay(str(message.id), conversation.status)


ACTION_CLOSE = "conversation_close"
ACTION_REOPEN = "conversation_reopen"

STATUS_CLOSED_TEXT = "🔒 This conversation is closed. Reply in this thread if you need more help."
STATUS_REOPENED_TEXT = "↩️ This conversation was reopened. A Cyflare analyst will follow up here."


def _primary_thread(conversation_id) -> SlackThread | None:
    return SlackThread.objects.filter(conversation_id=conversation_id).order_by("created_at").first()


def _active_client(thread: SlackThread) -> SlackClient | None:
    install = SlackInstallation.objects.filter(team_id=thread.team_id, status=InstallationStatus.ACTIVE).first()
    return SlackClient(decrypt_token(install.bot_token_encrypted)) if install else None


def resolved_blocks(text: str, conversation_id: str) -> list[dict]:
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": ACTION_CLOSE,
                    "text": {"type": "plain_text", "text": "✅ Close it"},
                    "style": "primary",
                    "value": conversation_id,
                },
                {
                    "type": "button",
                    "action_id": ACTION_REOPEN,
                    "text": {"type": "plain_text", "text": "↩️ I still need help"},
                    "value": conversation_id,
                },
            ],
        },
    ]


def post_status_to_slack(message: Message, status: str) -> None:
    """Post a status change or system notice into the thread; resolved notices get Close/Reopen buttons."""
    if (message.metadata or {}).get("slack_posted_ts"):
        return
    thread = _primary_thread(message.conversation_id)
    slack = _active_client(thread) if thread else None
    if not slack:
        return

    extra = {}
    if status == ConversationStatus.RESOLVED:
        text = f"✅ {message.body_plain}"
        extra["blocks"] = resolved_blocks(text, str(message.conversation_id))
    elif status == ConversationStatus.CLOSED:
        text = STATUS_CLOSED_TEXT
    elif status == ConversationStatus.WAITING_SOC:
        text = STATUS_REOPENED_TEXT
    else:
        text = message.body_plain  # e.g. the idle check-in nudge

    response = slack.post_message(thread.channel_id, text, thread_ts=thread.thread_ts or None, **extra)
    message.metadata = {**(message.metadata or {}), "slack_posted_ts": response.get("ts", "")}
    message.save(update_fields=["metadata"])


def post_to_slack(message: Message, sender_name: str) -> None:
    """Post ``message`` into the conversation's primary Slack thread (the first one it was linked to)."""
    if (message.metadata or {}).get("slack_posted_ts"):
        return  # already posted (task retry)
    thread = _primary_thread(message.conversation_id)
    if not thread:
        return
    slack = _active_client(thread)
    if not slack:
        logger.info("Skipping Slack delivery for message %s: workspace %s not active", message.id, thread.team_id)
        return

    thread_ts = thread.thread_ts or None
    if message.actor_type == ActorType.ANALYST:
        # chat:write.customize shows the analyst's name on the bot's post.
        response = slack.post_message(thread.channel_id, message.body_plain, thread_ts=thread_ts,
                                      username=f"{sender_name} · Cyflare SOC")
    else:
        text = f"*{sender_name}* (via Cyflare app):\n{message.body_plain}"
        response = slack.post_message(thread.channel_id, text, thread_ts=thread_ts)

    message.metadata = {**(message.metadata or {}), "slack_posted_ts": response.get("ts", "")}
    message.save(update_fields=["metadata"])
