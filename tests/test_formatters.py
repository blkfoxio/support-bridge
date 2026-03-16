"""Tests for Roam message formatters."""

from apps.integrations_roam.formatters import (
    format_customer_message,
    format_root_message,
    format_system_note,
)


class TestRoamFormatters:
    def test_root_message_contains_all_context(self):
        msg = format_root_message(
            customer_name="Jane Smith",
            customer_email="jane@acme.com",
            org_name="Acme Corp",
            org_id="37",
            tier="Enterprise",
            severity="High",
            issue_category="Incident",
            queue_name="incident-response",
            conversation_id="abc-123-def-456",
            message_body="We are seeing failed logins across multiple tenants.",
        )

        assert "Jane Smith" in msg
        assert "jane@acme.com" in msg
        assert "Acme Corp" in msg
        assert "37" in msg
        assert "Enterprise" in msg
        assert "High" in msg
        assert "Incident" in msg
        assert "incident-response" in msg
        assert "abc-123-def-456" in msg
        assert "We are seeing failed logins" in msg

    def test_customer_message_includes_identity(self):
        msg = format_customer_message(
            customer_name="Jane Smith",
            org_name="Acme Corp",
            message_body="We've confirmed this affects 3 tenants so far.",
        )

        assert "Jane Smith" in msg
        assert "Acme Corp" in msg
        assert "We've confirmed this affects 3 tenants" in msg

    def test_system_note_formatting(self):
        msg = format_system_note(note="Conversation transferred to billing-support queue")
        assert "transferred to billing-support" in msg
