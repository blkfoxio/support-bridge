"""Signed action tokens for Roam button URLs.

Generates HMAC-signed tokens so that action URLs embedded in Roam messages
can't be forged. Tokens are scoped to a specific action + conversation ID.
"""

import hashlib
import hmac

from django.conf import settings


def _signing_key() -> bytes:
    return settings.SECRET_KEY.encode()


def generate_action_token(action: str, conversation_id: str) -> str:
    """Generate a signed token for an action URL."""
    payload = f"{action}:{conversation_id}"
    return hmac.new(_signing_key(), payload.encode(), hashlib.sha256).hexdigest()


def verify_action_token(action: str, conversation_id: str, token: str) -> bool:
    """Verify a signed action token."""
    expected = generate_action_token(action, conversation_id)
    return hmac.compare_digest(expected, token)
