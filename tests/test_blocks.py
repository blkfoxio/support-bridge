"""Tests for Roam Block Kit message builders."""

import pytest

from apps.integrations_roam.blocks import (
    build_root_message_blocks,
    context,
    divider,
    header,
    section,
    url_button,
)


class TestBlockHelpers:
    def test_header_block(self):
        block = header("Hello World")
        assert block == {
            "type": "header",
            "text": {"type": "plain_text", "text": "Hello World"},
        }

    def test_section_markdown(self):
        block = section("*bold* text")
        assert block == {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*bold* text"},
        }

    def test_section_plain_text(self):
        block = section("plain", markdown=False)
        assert block["text"]["type"] == "plain_text"

    def test_context_block(self):
        block = context(["item 1", "item 2"])
        assert block["type"] == "context"
        assert len(block["elements"]) == 2
        assert block["elements"][0] == {"type": "mrkdwn", "text": "item 1"}

    def test_divider_block(self):
        assert divider() == {"type": "divider"}

    def test_url_button(self):
        btn = url_button("Click me", "https://example.com")
        assert btn["type"] == "button"
        assert btn["text"] == {"type": "plain_text", "text": "Click me"}
        assert btn["url"] == "https://example.com"
        assert "style" not in btn

    def test_url_button_with_style(self):
        btn = url_button("Danger!", "https://example.com", style="danger")
        assert btn["style"] == "danger"


@pytest.mark.django_db
class TestBuildRootMessageBlocks:
    """Tests for the composite root message builder."""

    SAMPLE_KWARGS = {
        "customer_name": "Jane Smith",
        "customer_email": "jane@acme.com",
        "org_name": "Acme Corp",
        "org_id": "42",
        "tier": "Enterprise",
        "severity": "high",
        "issue_category": "Incident",
        "queue_name": "incident-response",
        "conversation_id": "abc-123",
        "message_body": "We are seeing failed logins.",
    }

    def test_returns_blocks_and_color(self):
        blocks, color = build_root_message_blocks(**self.SAMPLE_KWARGS)
        assert isinstance(blocks, list)
        assert isinstance(color, str)

    def test_block_count_within_limit(self):
        blocks, _ = build_root_message_blocks(**self.SAMPLE_KWARGS)
        assert len(blocks) == 7
        assert len(blocks) <= 10

    def test_block_types_in_order(self):
        blocks, _ = build_root_message_blocks(**self.SAMPLE_KWARGS)
        expected_types = [
            "header",
            "section",
            "section",
            "context",
            "context",
            "divider",
            "section",
        ]
        assert [b["type"] for b in blocks] == expected_types

    def test_header_text(self):
        blocks, _ = build_root_message_blocks(**self.SAMPLE_KWARGS)
        assert blocks[0]["text"]["text"] == "New Support Conversation"

    def test_customer_info_in_blocks(self):
        blocks, _ = build_root_message_blocks(**self.SAMPLE_KWARGS)
        customer_text = blocks[1]["text"]["text"]
        assert "Jane Smith" in customer_text
        assert "jane@acme.com" in customer_text

    def test_org_info_in_blocks(self):
        blocks, _ = build_root_message_blocks(**self.SAMPLE_KWARGS)
        org_text = blocks[2]["text"]["text"]
        assert "Acme Corp" in org_text
        assert "42" in org_text

    def test_triage_context(self):
        blocks, _ = build_root_message_blocks(**self.SAMPLE_KWARGS)
        context_elements = [el["text"] for el in blocks[3]["elements"]]
        combined = " ".join(context_elements)
        assert "Enterprise" in combined
        assert "high" in combined
        assert "Incident" in combined

    def test_queue_context(self):
        blocks, _ = build_root_message_blocks(**self.SAMPLE_KWARGS)
        context_elements = [el["text"] for el in blocks[4]["elements"]]
        combined = " ".join(context_elements)
        assert "incident-response" in combined
        assert "abc-123" in combined

    def test_message_body_in_last_section(self):
        blocks, _ = build_root_message_blocks(**self.SAMPLE_KWARGS)
        body_text = blocks[6]["text"]["text"]
        assert "We are seeing failed logins." in body_text

    def test_severity_color_mapping(self):
        for severity, expected_color in [
            ("critical", "danger"),
            ("high", "warning"),
            ("medium", "#DE9E36"),
            ("low", "#17A2B8"),
        ]:
            kwargs = {**self.SAMPLE_KWARGS, "severity": severity}
            _, color = build_root_message_blocks(**kwargs)
            assert color == expected_color, f"severity={severity}: expected {expected_color}, got {color}"

    def test_unknown_severity_uses_fallback(self):
        kwargs = {**self.SAMPLE_KWARGS, "severity": "unknown-level"}
        _, color = build_root_message_blocks(**kwargs)
        assert color == "#888888"

    def test_long_message_body_truncated(self):
        long_body = "x" * 7000
        kwargs = {**self.SAMPLE_KWARGS, "message_body": long_body}
        blocks, _ = build_root_message_blocks(**kwargs)
        body_text = blocks[6]["text"]["text"]
        assert len(body_text) < 7000
        assert "truncated" in body_text
