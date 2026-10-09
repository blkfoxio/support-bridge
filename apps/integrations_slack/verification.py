"""Slack request signature verification (https://api.slack.com/authentication/verifying-requests-from-slack)."""

import hashlib
import hmac
import time

from django.conf import settings

MAX_REQUEST_AGE_SECONDS = 60 * 5


def verify_slack_signature(*, body: bytes, timestamp: str, signature: str, now: float | None = None) -> bool:
    secret = getattr(settings, "SLACK_SIGNING_SECRET", "")
    if not secret or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs((now or time.time()) - ts) > MAX_REQUEST_AGE_SECONDS:
        return False

    basestring = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
