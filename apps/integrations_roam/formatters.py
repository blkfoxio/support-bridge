"""Format messages for posting to Roam so analysts have full customer context."""


def format_root_message(
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
) -> str:
    """Format the first message posted to a Roam thread when a conversation is created.

    Includes a rich context header so analysts can immediately see who the customer is
    and the triage details without leaving Roam.
    """
    return (
        f"📋 New Support Conversation ——————————————————————————————\n"
        f"\n"
        f"👤 Customer: {customer_name} ({customer_email})\n"
        f"🏢 Organization: {org_name} (ID: {org_id})\n"
        f"📊 Tier: {tier} | Severity: {severity} | Category: {issue_category}\n"
        f"🎯 Queue: {queue_name}\n"
        f"🔗 Conversation ID: {conversation_id}\n"
        f"\n"
        f"——————————————————————————————————————————————————————————\n"
        f"\n"
        f"{message_body}"
    )


def format_customer_message(
    *,
    customer_name: str,
    org_name: str,
    message_body: str,
) -> str:
    """Format a follow-up customer message posted to an existing Roam thread.

    Prefixed with customer identity so analysts always know who's talking.
    """
    return f"💬 {customer_name} ({org_name}):\n{message_body}"


def format_system_note(*, note: str) -> str:
    """Format a system-generated note (e.g. transfer, status change)."""
    return f"⚙️ {note}"
