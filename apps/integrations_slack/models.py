from django.db import models


class InstallationStatus(models.TextChoices):
    PENDING = "pending", "Pending (not yet linked to an org)"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive (uninstalled or revoked)"


class SlackInstallation(models.Model):
    """The Cyflare Slack app installed in one customer workspace."""

    id = models.BigAutoField(primary_key=True)
    team_id = models.CharField(max_length=32, unique=True, help_text="Slack workspace ID (T…)")
    team_name = models.CharField(max_length=255, default="", blank=True)
    enterprise_id = models.CharField(max_length=32, default="", blank=True, help_text="Enterprise Grid ID (E…)")

    # Null until the install is linked to a Cyflare ONE org (installs started from Slack begin pending).
    org_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=InstallationStatus.choices, default=InstallationStatus.PENDING)

    bot_user_id = models.CharField(max_length=32, default="", blank=True)
    bot_token_encrypted = models.TextField(help_text="Fernet-encrypted bot token (xoxb-…)")
    scopes = models.TextField(default="", blank=True)

    installed_by_slack_user_id = models.CharField(max_length=32, default="", blank=True)
    linked_by_user_id = models.CharField(
        max_length=255, default="", blank=True, help_text="Cyflare ONE user who linked the install to the org"
    )
    claim_code_hash = models.CharField(max_length=64, default="", blank=True)
    claim_expires_at = models.DateTimeField(null=True, blank=True)

    installed_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-installed_at"]

    def __str__(self):
        return f"{self.team_name or self.team_id} ({self.status})"


class SlackChannel(models.Model):
    """A channel (or DM) the bot is a member of in a customer workspace."""

    id = models.BigAutoField(primary_key=True)
    installation = models.ForeignKey(SlackInstallation, on_delete=models.CASCADE, related_name="channels")
    channel_id = models.CharField(max_length=32)
    name = models.CharField(max_length=255, default="", blank=True)
    is_private = models.BooleanField(default=False)
    is_im = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True, help_text="Disabled channels are ignored")
    conversation_trigger = models.CharField(
        max_length=20,
        default="",
        blank=True,
        help_text="Overrides the org's conversation trigger when set (all_messages or emoji)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["installation", "channel_id"], name="unique_slack_channel"),
        ]

    def __str__(self):
        return f"#{self.name or self.channel_id} ({self.installation.team_id})"


class SlackThread(models.Model):
    """Maps a Slack thread (or a DM) to a conversation.

    A conversation can have several rows (e.g. merged top-level posts). A thread can map
    to a newer conversation after the old one closes, so lookups take the newest row.
    DMs use an empty ``thread_ts`` and post flat, without threading.
    """

    id = models.BigAutoField(primary_key=True)
    conversation = models.ForeignKey(
        "conversations.Conversation", on_delete=models.CASCADE, related_name="slack_threads"
    )
    team_id = models.CharField(max_length=32)
    channel_id = models.CharField(max_length=32)
    thread_ts = models.CharField(max_length=32, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["team_id", "channel_id", "thread_ts"], name="idx_slack_thread_lookup"),
        ]

    def __str__(self):
        return f"{self.team_id}/{self.channel_id}/{self.thread_ts or 'dm'} → {self.conversation_id}"
