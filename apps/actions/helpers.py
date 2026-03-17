"""Helpers for building action URLs."""

from django.conf import settings

from .tokens import generate_action_token


def _base_url() -> str:
    """Get the public base URL for action pages."""
    # Use SITE_URL if configured, otherwise fall back to a sensible default.
    return getattr(settings, "SITE_URL", "https://support-bridge-production.up.railway.app")


def resolve_action_url(conversation_id: str) -> str:
    """Build the signed URL for the 'Resolve' button in Roam."""
    token = generate_action_token("resolve", conversation_id)
    return f"{_base_url()}/actions/resolve/{conversation_id}/?token={token}"
