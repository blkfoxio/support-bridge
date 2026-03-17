"""Roam Block Kit message builders.

Builds structured JSON block arrays for the Roam chat.post API.
See https://developer.ro.am/docs/guides/block-kit

Constraints:
  - Max 10 blocks per message
  - Max 8 000 bytes payload
  - ``blocks`` and ``text`` are mutually exclusive in the API payload
"""

from __future__ import annotations

from apps.actions.helpers import resolve_action_url

from .theme import get_theme, severity_color

# Max length for message body before truncation (keeps payload under 8KB).
_MAX_BODY_LENGTH = 6000


# ---------------------------------------------------------------------------
# Block helpers
# ---------------------------------------------------------------------------


def header(text: str) -> dict:
    """Header block — large bold text (plain_text only)."""
    return {"type": "header", "text": {"type": "plain_text", "text": text}}


def section(text: str, *, markdown: bool = True) -> dict:
    """Section block — primary content area."""
    text_type = "mrkdwn" if markdown else "plain_text"
    return {"type": "section", "text": {"type": text_type, "text": text}}


def context(elements: list[str]) -> dict:
    """Context block — small supplementary metadata."""
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": el} for el in elements],
    }


def divider() -> dict:
    """Divider block — horizontal separator."""
    return {"type": "divider"}


def url_button(text: str, url: str, *, style: str | None = None) -> dict:
    """URL button element — opens a link when clicked."""
    btn: dict = {
        "type": "button",
        "text": {"type": "plain_text", "text": text},
        "url": url,
    }
    if style:
        btn["style"] = style
    return btn


def actions(buttons: list[dict]) -> dict:
    """Actions block — row of up to 8 buttons."""
    return {"type": "actions", "elements": buttons[:8]}


# ---------------------------------------------------------------------------
# Composite builders
# ---------------------------------------------------------------------------


def build_root_message_blocks(
    *,
    customer_name: str,
    customer_email: str,
    org_name: str,
    org_id: str,
    tier: str,
    severity: str,
    issue_category: str,
    queue_name: str,
    conversation_id: str,
    message_body: str,
) -> tuple[list[dict], str]:
    """Build Block Kit blocks + color for a new conversation root message.

    Returns:
        (blocks, color) tuple ready for ``RoamClient.post_blocks()``.
        ``blocks`` is a list of 8 block dicts (within the 10-block limit).
        ``color`` is a Roam color value for the left strip.
    """
    theme = get_theme(org_id)

    # Truncate long messages to stay within 8KB payload limit.
    body = message_body
    if len(body) > _MAX_BODY_LENGTH:
        body = body[:_MAX_BODY_LENGTH] + "\n\n_(message truncated)_"

    resolve_url = resolve_action_url(conversation_id)

    blocks = [
        header(theme["header_text"]),
        section(f"*Customer:* {customer_name} ({customer_email})"),
        section(f"*Organization:* {org_name} (ID: {org_id})"),
        context([
            f"*Tier:* {tier}",
            f"*Severity:* {severity}",
            f"*Category:* {issue_category}",
        ]),
        context([
            f"*Queue:* {queue_name}",
            f"*ID:* {conversation_id}",
        ]),
        divider(),
        section(body),
        actions([url_button("Resolve", resolve_url, style="primary")]),
    ]

    color = severity_color(severity, org_id)

    return blocks, color
