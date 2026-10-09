from django.db import models


class SlackConversationTrigger(models.TextChoices):
    ALL_MESSAGES = "all_messages", "Every top-level message"
    EMOJI = "emoji", "Only messages given the trigger emoji"


class Organization(models.Model):
    """A customer organization, keyed by the Cyflare ONE org ID.

    Conversations still reference orgs by the loose ``customer_org_id`` string;
    this table holds per-org settings (e.g. for the Slack integration) and is
    populated lazily as conversations are created.
    """

    id = models.BigAutoField(primary_key=True)
    org_id = models.CharField(max_length=100, unique=True, help_text="Cyflare ONE organization ID")
    name = models.CharField(max_length=255, default="", blank=True)

    # Slack integration settings
    slack_allow_unlinked_users = models.BooleanField(
        default=True,
        help_text="Allow Slack users without a linked Cyflare ONE account to start conversations",
    )
    slack_merge_window_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Top-level Slack posts from the same person within this window join their open conversation",
    )
    slack_conversation_trigger = models.CharField(
        max_length=20,
        choices=SlackConversationTrigger.choices,
        default=SlackConversationTrigger.ALL_MESSAGES,
        help_text="What starts a conversation in a Slack channel (channels can override)",
    )
    slack_trigger_emoji = models.CharField(
        max_length=64, default="speech_balloon", help_text="Reaction name used when the trigger is 'emoji'"
    )
    slack_auto_join_pattern = models.CharField(
        max_length=100,
        default="",
        blank=True,
        help_text="Glob for public channel names the bot joins automatically, e.g. cyflare-*",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name or self.org_id} ({self.org_id})"
