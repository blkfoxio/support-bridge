"""Slack installation lifecycle: record installs, link them to orgs, deactivate on uninstall."""

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.organizations.services import ensure_organization

from .client import SlackClient
from .crypto import decrypt_token, encrypt_token
from .models import InstallationStatus, SlackInstallation

logger = logging.getLogger(__name__)


class InstallConflictError(Exception):
    """The workspace is already connected to a different org."""


class InvalidClaimError(Exception):
    """The claim code is unknown, already used, or expired."""


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@transaction.atomic
def record_installation(
    oauth: dict, *, org_id: str | None, user_id: str | None
) -> tuple[SlackInstallation, str | None]:
    """Create or refresh the installation from an oauth.v2.access response.

    With ``org_id`` (started from Cyflare ONE) the install is active immediately.
    Without it (started from Slack) the install stays pending and a claim code is returned
    for an org member to link it in Cyflare ONE; reinstalling an already-active workspace
    just refreshes its token.
    """
    team = oauth.get("team") or {}
    team_id = team.get("id")
    if not team_id:
        raise ValueError("oauth.v2.access response has no team id")

    install = SlackInstallation.objects.select_for_update().filter(team_id=team_id).first()
    is_active = install is not None and install.status == InstallationStatus.ACTIVE
    if org_id and is_active and install.org_id != org_id:
        raise InstallConflictError(f"Workspace {team_id} is already connected to another organization")

    install = install or SlackInstallation(team_id=team_id)
    install.team_name = team.get("name", "") or install.team_name
    install.enterprise_id = (oauth.get("enterprise") or {}).get("id", "") or ""
    install.bot_user_id = oauth.get("bot_user_id", "")
    install.bot_token_encrypted = encrypt_token(oauth["access_token"])
    install.scopes = oauth.get("scope", "")
    install.installed_by_slack_user_id = (oauth.get("authed_user") or {}).get("id", "")
    install.deactivated_at = None

    claim_code = None
    now = timezone.now()
    if org_id:
        install.org_id = org_id
        install.linked_by_user_id = user_id or ""
        install.status = InstallationStatus.ACTIVE
        install.activated_at = install.activated_at if is_active else now
        install.claim_code_hash = ""
        install.claim_expires_at = None
        ensure_organization(org_id)
    elif is_active:
        pass  # reinstall from Slack (e.g. scope change); keep the existing org link
    else:
        claim_code = secrets.token_urlsafe(12)
        install.org_id = None
        install.status = InstallationStatus.PENDING
        install.claim_code_hash = _hash_code(claim_code)
        install.claim_expires_at = now + timedelta(days=getattr(settings, "SLACK_CLAIM_TTL_DAYS", 7))
    install.save()
    return install, claim_code


@transaction.atomic
def claim_installation(code: str, *, org_id: str, user_id: str) -> SlackInstallation:
    """Link a pending installation to ``org_id`` using its claim code."""
    install = (
        SlackInstallation.objects.select_for_update()
        .filter(claim_code_hash=_hash_code(code), status=InstallationStatus.PENDING)
        .first()
    )
    if not install or not install.claim_expires_at or install.claim_expires_at < timezone.now():
        raise InvalidClaimError("Invalid or expired claim code")

    install.org_id = org_id
    install.linked_by_user_id = user_id
    install.status = InstallationStatus.ACTIVE
    install.activated_at = timezone.now()
    install.claim_code_hash = ""
    install.claim_expires_at = None
    install.save()
    ensure_organization(org_id)
    return install


def deactivate_installation(team_id: str, *, reason: str) -> bool:
    """Mark a workspace's install inactive (app uninstalled or tokens revoked)."""
    updated = SlackInstallation.objects.filter(team_id=team_id).exclude(status=InstallationStatus.INACTIVE).update(
        status=InstallationStatus.INACTIVE, deactivated_at=timezone.now()
    )
    if updated:
        logger.info("Deactivated Slack installation team=%s reason=%s", team_id, reason)
    return bool(updated)


def notify_installer(install: SlackInstallation, text: str) -> None:
    """DM the person who installed the app. Best effort: failures are logged, not raised."""
    if not install.installed_by_slack_user_id:
        return
    try:
        SlackClient(decrypt_token(install.bot_token_encrypted)).post_message(install.installed_by_slack_user_id, text)
    except Exception:
        logger.exception("Failed to DM Slack installer for team %s", install.team_id)
