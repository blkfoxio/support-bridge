"""Verify a customer's organization membership against the Cyflare ONE API.

Cognito access tokens don't carry the org, so the org a client sends is checked
against the organizations ONE says the caller can access, using the caller's
own bearer token. Results are cached briefly per user and org.
"""

import json
import logging

import httpx
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_AUTOCOMPLETE_PATH = "/v1/organization/administrative/organizationautocomplete/"
_PAGE_SIZE = 100
_MAX_PAGES = 20


class OrgVerificationUnavailableError(Exception):
    """Cyflare ONE could not be reached or returned an unexpected response."""


def org_verification_enabled() -> bool:
    return bool(getattr(settings, "CYFLARE_ONE_API_BASE_URL", ""))


def _collect_ids(items, ids: set[str]) -> None:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if item.get("id") is not None and not item.get("disabled"):
            ids.add(str(item["id"]))
        children = item.get("children")
        if isinstance(children, str):
            try:
                children = json.loads(children)
            except ValueError:
                children = None
        if isinstance(children, list):
            _collect_ids(children, ids)


def fetch_accessible_org_ids(token: str) -> set[str]:
    """Return the IDs of every organization the token's user can access in Cyflare ONE.

    Returns an empty set if ONE rejects the token (401/403).
    Raises OrgVerificationUnavailableError on network errors, timeouts, or other bad responses.
    """
    base_url = settings.CYFLARE_ONE_API_BASE_URL.rstrip("/")
    timeout = getattr(settings, "CYFLARE_ONE_TIMEOUT_SECONDS", 3.0)
    ids: set[str] = set()
    try:
        with httpx.Client(timeout=timeout) as client:
            for page in range(_MAX_PAGES):
                resp = client.get(
                    base_url + _AUTOCOMPLETE_PATH,
                    params={"$top": _PAGE_SIZE, "$skip": page * _PAGE_SIZE},
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code in (401, 403):
                    logger.warning("Cyflare ONE rejected token for org lookup (status=%s)", resp.status_code)
                    return set()
                resp.raise_for_status()
                data = resp.json()
                _collect_ids(data.get("results"), ids)
                if not data.get("next"):
                    break
    except (httpx.HTTPError, ValueError) as e:
        raise OrgVerificationUnavailableError(str(e)) from e
    return ids


def user_can_access_org(*, token: str, uid: str, org_id: str) -> bool:
    """Check (with caching) whether the authenticated user belongs to ``org_id``.

    Raises OrgVerificationUnavailableError when ONE can't answer; callers should fail closed.
    """
    cache_key = f"one_org_access:{uid}:{org_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    allowed = str(org_id) in fetch_accessible_org_ids(token)
    ttl = getattr(settings, "CYFLARE_ONE_ORG_CACHE_SECONDS", 600)
    # Cache denials briefly so a newly added user isn't locked out for long.
    cache.set(cache_key, allowed, ttl if allowed else min(ttl, 60))
    return allowed
