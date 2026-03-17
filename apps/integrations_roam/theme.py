"""Theme resolution for Roam Block Kit messages.

Four-layer resolution chain (highest priority first):
  1. BrandingConfig for the specific org_id (DB per-org)
  2. BrandingConfig with org_id=NULL (DB deployment default)
  3. settings.ROAM_THEME dict (Django settings file)
  4. Hardcoded defaults below (Cyflare design system)

Override via Django settings::

    ROAM_THEME = {
        "severity_colors": {"critical": "#FF0000", "high": "#FFA500"},
        "header_text": "New Support Request",
        "fallback_color": "#999999",
    }

Or via the admin API — create/update a BrandingConfig record.
"""

from django.conf import settings

# ---------------------------------------------------------------------------
# Hardcoded defaults — Cyflare design system (aligned with casi-mobile AppColors)
# ---------------------------------------------------------------------------

DEFAULT_SEVERITY_COLORS: dict[str, str] = {
    "critical": "danger",   # AppColors.danger  #EF4444 → Roam "danger" (red strip)
    "high": "warning",      # AppColors.warning #F59E0B → Roam "warning" (amber strip)
    "medium": "#DE9E36",    # AppColors.accent
    "low": "#17A2B8",       # AppColors.info
}

DEFAULT_HEADER_TEXT = "New Support Conversation"

DEFAULT_FALLBACK_COLOR = "#888888"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_theme(org_id: str | None = None) -> dict:
    """Resolve the merged theme for a given org.

    Merges all four layers so that higher-priority layers override lower ones.
    Only non-empty values from each layer are applied.
    """
    # Layer 1: hardcoded defaults
    severity_colors = {**DEFAULT_SEVERITY_COLORS}
    header_text = DEFAULT_HEADER_TEXT
    fallback_color = DEFAULT_FALLBACK_COLOR

    # Layer 2: Django settings overrides
    settings_theme = getattr(settings, "ROAM_THEME", {})
    if isinstance(settings_theme, dict):
        severity_colors.update(settings_theme.get("severity_colors", {}))
        header_text = settings_theme.get("header_text") or header_text
        fallback_color = settings_theme.get("fallback_color") or fallback_color

    # Layer 3: DB deployment default (org_id IS NULL)
    from apps.admin_config.models import BrandingConfig  # late import to avoid circular

    try:
        db_default = BrandingConfig.objects.filter(org_id__isnull=True).first()
    except Exception:
        # DB not available (e.g. during migrations or tests without DB)
        db_default = None

    if db_default:
        if db_default.severity_colors:
            severity_colors.update(
                {k: v for k, v in db_default.severity_colors.items() if v}
            )
        if db_default.header_text:
            header_text = db_default.header_text
        if db_default.fallback_color:
            fallback_color = db_default.fallback_color

    # Layer 4: DB per-org override
    if org_id:
        try:
            db_org = BrandingConfig.objects.filter(org_id=org_id).first()
        except Exception:
            db_org = None

        if db_org:
            if db_org.severity_colors:
                severity_colors.update(
                    {k: v for k, v in db_org.severity_colors.items() if v}
                )
            if db_org.header_text:
                header_text = db_org.header_text
            if db_org.fallback_color:
                fallback_color = db_org.fallback_color

    return {
        "severity_colors": severity_colors,
        "header_text": header_text,
        "fallback_color": fallback_color,
    }


def severity_color(severity: str, org_id: str | None = None) -> str:
    """Map a severity level to its Roam Block Kit color value."""
    theme = get_theme(org_id)
    return theme["severity_colors"].get(severity.lower(), theme["fallback_color"])
