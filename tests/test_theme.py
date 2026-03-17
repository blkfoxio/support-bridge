"""Tests for the theme resolution system."""

import pytest
from django.test import override_settings

from apps.admin_config.models import BrandingConfig
from apps.integrations_roam.theme import (
    DEFAULT_FALLBACK_COLOR,
    DEFAULT_HEADER_TEXT,
    DEFAULT_SEVERITY_COLORS,
    get_theme,
    severity_color,
)


class TestDefaultTheme:
    """Test hardcoded defaults without DB or settings overrides."""

    def test_default_severity_colors(self):
        assert DEFAULT_SEVERITY_COLORS == {
            "critical": "danger",
            "high": "warning",
            "medium": "#DE9E36",
            "low": "#17A2B8",
        }

    def test_default_header_text(self):
        assert DEFAULT_HEADER_TEXT == "New Support Conversation"

    def test_default_fallback_color(self):
        assert DEFAULT_FALLBACK_COLOR == "#888888"


@pytest.mark.django_db
class TestSeverityColor:
    def test_critical(self):
        assert severity_color("critical") == "danger"

    def test_high(self):
        assert severity_color("high") == "warning"

    def test_medium(self):
        assert severity_color("medium") == "#DE9E36"

    def test_low(self):
        assert severity_color("low") == "#17A2B8"

    def test_case_insensitive(self):
        assert severity_color("CRITICAL") == "danger"
        assert severity_color("High") == "warning"

    def test_unknown_severity_returns_fallback(self):
        assert severity_color("unknown") == "#888888"


@pytest.mark.django_db
class TestSettingsOverride:
    @override_settings(ROAM_THEME={"severity_colors": {"critical": "#FF0000"}})
    def test_settings_override_single_color(self):
        theme = get_theme()
        assert theme["severity_colors"]["critical"] == "#FF0000"
        # Other colors remain at defaults
        assert theme["severity_colors"]["high"] == "warning"

    @override_settings(ROAM_THEME={"header_text": "Custom Header"})
    def test_settings_override_header_text(self):
        theme = get_theme()
        assert theme["header_text"] == "Custom Header"

    @override_settings(ROAM_THEME={"fallback_color": "#AAAAAA"})
    def test_settings_override_fallback_color(self):
        theme = get_theme()
        assert theme["fallback_color"] == "#AAAAAA"


@pytest.mark.django_db
class TestDbDefaultOverride:
    """DB default (org_id=None) overrides Django settings."""

    def test_db_default_overrides_hardcoded(self):
        BrandingConfig.objects.create(
            org_id=None,
            severity_colors={"critical": "#DB0000"},
            header_text="DB Default Header",
        )

        theme = get_theme()
        assert theme["severity_colors"]["critical"] == "#DB0000"
        assert theme["header_text"] == "DB Default Header"
        # Non-overridden colors stay at default
        assert theme["severity_colors"]["high"] == "warning"

    @override_settings(ROAM_THEME={"severity_colors": {"critical": "#SETTINGS"}})
    def test_db_default_overrides_settings(self):
        BrandingConfig.objects.create(
            org_id=None,
            severity_colors={"critical": "#FROMDB"},
        )

        theme = get_theme()
        # DB wins over settings
        assert theme["severity_colors"]["critical"] == "#FROMDB"

    def test_empty_db_fields_do_not_override(self):
        BrandingConfig.objects.create(
            org_id=None,
            severity_colors={},
            header_text="",
            fallback_color="",
        )

        theme = get_theme()
        assert theme["header_text"] == DEFAULT_HEADER_TEXT
        assert theme["fallback_color"] == DEFAULT_FALLBACK_COLOR
        assert theme["severity_colors"] == DEFAULT_SEVERITY_COLORS


@pytest.mark.django_db
class TestDbPerOrgOverride:
    """DB per-org (org_id != None) overrides DB default."""

    def test_per_org_overrides_default(self):
        BrandingConfig.objects.create(
            org_id=None,
            severity_colors={"critical": "#DEFAULT"},
            header_text="Default Header",
        )
        BrandingConfig.objects.create(
            org_id="org-abc",
            severity_colors={"critical": "#ORG_ABC"},
            header_text="Org ABC Header",
        )

        theme = get_theme(org_id="org-abc")
        assert theme["severity_colors"]["critical"] == "#ORG_ABC"
        assert theme["header_text"] == "Org ABC Header"

    def test_per_org_merges_with_defaults(self):
        BrandingConfig.objects.create(
            org_id="org-abc",
            severity_colors={"critical": "#CUSTOM"},
        )

        theme = get_theme(org_id="org-abc")
        # Overridden
        assert theme["severity_colors"]["critical"] == "#CUSTOM"
        # Defaults preserved
        assert theme["severity_colors"]["high"] == "warning"
        assert theme["severity_colors"]["medium"] == "#DE9E36"
        assert theme["severity_colors"]["low"] == "#17A2B8"

    def test_nonexistent_org_uses_defaults(self):
        theme = get_theme(org_id="nonexistent-org")
        assert theme["severity_colors"] == DEFAULT_SEVERITY_COLORS
        assert theme["header_text"] == DEFAULT_HEADER_TEXT

    def test_no_org_id_returns_default_theme(self):
        theme = get_theme(org_id=None)
        assert theme["severity_colors"] == DEFAULT_SEVERITY_COLORS

    def test_severity_color_with_org_id(self):
        BrandingConfig.objects.create(
            org_id="org-xyz",
            severity_colors={"critical": "#ORGCOLOR"},
        )

        assert severity_color("critical", org_id="org-xyz") == "#ORGCOLOR"
        # Other org uses default
        assert severity_color("critical", org_id="other-org") == "danger"
