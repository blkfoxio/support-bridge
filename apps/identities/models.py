from django.db import models


class IdentityProvider(models.TextChoices):
    SLACK = "slack", "Slack"


class ExternalIdentity(models.Model):
    """A customer as known to an external chat platform (e.g. a Slack user), optionally linked to a ONE account."""

    id = models.BigAutoField(primary_key=True)
    provider = models.CharField(max_length=20, choices=IdentityProvider.choices)
    team_id = models.CharField(max_length=64, help_text="Workspace/tenant ID on the provider")
    external_user_id = models.CharField(max_length=64, help_text="User ID on the provider")
    org_id = models.CharField(max_length=100, db_index=True)

    email = models.CharField(max_length=255, default="", blank=True, db_index=True)
    display_name = models.CharField(max_length=255, default="", blank=True)

    linked_user_id = models.CharField(
        max_length=255, null=True, blank=True, db_index=True, help_text="Cyflare ONE user ID once linked"
    )
    linked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "team_id", "external_user_id"], name="unique_external_identity"
            ),
        ]

    @property
    def synthetic_user_id(self) -> str:
        """Stand-in customer ID used until the identity is linked to a ONE account."""
        return f"{self.provider}:{self.team_id}:{self.external_user_id}"

    @property
    def effective_user_id(self) -> str:
        return self.linked_user_id or self.synthetic_user_id

    def __str__(self):
        return f"{self.display_name or self.external_user_id} ({self.provider}:{self.team_id})"
