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
