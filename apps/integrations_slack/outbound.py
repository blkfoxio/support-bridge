"""Post outbound messages (analyst replies, messages sent from the Cyflare app) into the Slack thread."""

import logging

from apps.conversations.models import Conversation
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


def post_to_slack(message: Message, sender_name: str) -> None:
    """Post ``message`` into the conversation's primary Slack thread (the first one it was linked to)."""
    if (message.metadata or {}).get("slack_posted_ts"):
        return  # already posted (task retry)
    thread = SlackThread.objects.filter(conversation_id=message.conversation_id).order_by("created_at").first()
    if not thread:
        return
    install = SlackInstallation.objects.filter(team_id=thread.team_id, status=InstallationStatus.ACTIVE).first()
    if not install:
        logger.info("Skipping Slack delivery for message %s: workspace %s not active", message.id, thread.team_id)
        return

    slack = SlackClient(decrypt_token(install.bot_token_encrypted))
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
