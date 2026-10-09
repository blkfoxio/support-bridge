"""Slack OAuth v2 install flow: signed single-use state and code exchange."""

import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.core.cache import cache

from .client import SlackClient

# Bot scopes; keep minimal and justify each (Slack reviews these for distributed apps).
BOT_SCOPES = [
    "chat:write",  # reply in customer threads
    "chat:write.customize",  # show the analyst's name/avatar on replies
    "channels:history",  # read messages in public channels the bot is in
    "groups:history",  # read messages in private channels the bot is invited to
    "im:history",  # read DMs sent to the bot
    "channels:read",  # channel names; detect new channels for auto-join
    "groups:read",  # private channel names
    "channels:join",  # auto-join public channels matching the org's pattern
    "reactions:read",  # emoji conversation-trigger mode
    "users:read",  # display names
    "users:read.email",  # match Slack users to Cyflare ONE accounts
]

AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
_STATE_SALT = "slack-oauth-state"
STATE_MAX_AGE_SECONDS = 15 * 60


def redirect_uri() -> str:
    return f"{settings.SITE_URL.rstrip('/')}/slack/oauth/callback"


def build_authorize_url(*, org_id: str | None = None, user_id: str | None = None) -> str:
    """Return a Slack authorize URL. ``org_id`` is set when the install starts from Cyflare ONE."""
    nonce = secrets.token_urlsafe(16)
    cache.set(f"slack_oauth_state:{nonce}", 1, STATE_MAX_AGE_SECONDS)
    state = signing.dumps({"n": nonce, "org": org_id, "uid": user_id}, salt=_STATE_SALT)
    query = urlencode(
        {
            "client_id": settings.SLACK_CLIENT_ID,
            "scope": ",".join(BOT_SCOPES),
            "redirect_uri": redirect_uri(),
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def consume_state(state: str) -> dict | None:
    """Validate a state value and mark it used. Returns its payload, or None if invalid, expired or reused."""
    try:
        payload = signing.loads(state, salt=_STATE_SALT, max_age=STATE_MAX_AGE_SECONDS)
    except signing.BadSignature:
        return None
    if not cache.delete(f"slack_oauth_state:{payload.get('n')}"):
        return None
    return payload


def exchange_code(code: str) -> dict:
    """Exchange an OAuth code for a bot token via oauth.v2.access. Raises SlackApiError."""
    return SlackClient().call(
        "oauth.v2.access",
        data={
            "client_id": settings.SLACK_CLIENT_ID,
            "client_secret": settings.SLACK_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri(),
        },
    )
