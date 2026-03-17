"""Admin configuration models — branding, routing rules, etc."""

from django.db import models


class BrandingConfig(models.Model):
    """Per-organization branding overrides for Roam Block Kit messages.

    Resolution chain (highest priority first):
      1. BrandingConfig with matching org_id
      2. BrandingConfig with org_id=NULL (deployment-wide DB default)
      3. settings.ROAM_THEME dict
      4. Hardcoded defaults in theme.py

    org_id=None → deployment-wide default (at most one allowed).
    org_id="abc" → overrides for that specific customer org.
    """

    id = models.BigAutoField(primary_key=True)
    org_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        help_text="Customer org ID. Null = deployment-wide default.",
    )
    severity_colors = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Partial map of severity level → Roam color value. '
            'e.g. {"critical": "danger", "high": "#F59E0B"}. '
            "Merged with defaults; only specified keys are overridden."
        ),
    )
    header_text = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Header block text for new conversations. Empty = use deployment default.",
    )
    fallback_color = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Color for unknown severity levels. Empty = use deployment default.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Branding config"
        verbose_name_plural = "Branding configs"

    def __str__(self):
        return f"Branding: {self.org_id or 'default'}"
