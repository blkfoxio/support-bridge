"""Tests for the Slack app install flow, signature verification and lifecycle events."""

import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.integrations_slack import oauth
from apps.integrations_slack.crypto import decrypt_token, encrypt_token
from apps.integrations_slack.models import InstallationStatus, SlackInstallation
from apps.integrations_slack.services import (
    InstallConflictError,
    InvalidClaimError,
    claim_installation,
    record_installation,
)
from apps.integrations_slack.verification import verify_slack_signature
from apps.organizations.models import Organization

SIGNING_SECRET = "test-signing-secret"


@pytest.fixture(autouse=True)
def slack_settings(settings):
    settings.SLACK_CLIENT_ID = "123.456"
    settings.SLACK_CLIENT_SECRET = "client-secret"
    settings.SLACK_SIGNING_SECRET = SIGNING_SECRET
    settings.SLACK_TOKEN_ENCRYPTION_KEY = Fernet.generate_key().decode()
    settings.SLACK_CLAIM_URL = ""
    settings.SITE_URL = "https://bridge.test"
    settings.CYFLARE_ONE_API_BASE_URL = ""
    cache.clear()


def _oauth_response(team_id="T1", token="xoxb-secret", installer="U-installer"):
    return {
        "ok": True,
        "access_token": token,
        "scope": "chat:write,im:history",
        "bot_user_id": "B-bot",
        "team": {"id": team_id, "name": "Acme"},
        "enterprise": None,
        "authed_user": {"id": installer},
    }


def _signed_post(client, payload, *, secret=SIGNING_SECRET, ts=None):
    body = json.dumps(payload).encode()
    ts = str(int(ts or time.time()))
    sig = "v0=" + hmac.new(secret.encode(), b"v0:" + ts.encode() + b":" + body, hashlib.sha256).hexdigest()
    return client.post(
        "/slack/events", data=body, content_type="application/json",
        HTTP_X_SLACK_REQUEST_TIMESTAMP=ts, HTTP_X_SLACK_SIGNATURE=sig,
    )


# --- Signature verification ---


class TestVerifySlackSignature:
    def _sign(self, body, ts):
        return "v0=" + hmac.new(SIGNING_SECRET.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()

    def test_valid_signature(self):
        ts = str(int(time.time()))
        assert verify_slack_signature(body=b"{}", timestamp=ts, signature=self._sign(b"{}", ts))

    def test_tampered_body_rejected(self):
        ts = str(int(time.time()))
        assert not verify_slack_signature(body=b'{"x":1}', timestamp=ts, signature=self._sign(b"{}", ts))

    def test_stale_timestamp_rejected(self):
        ts = str(int(time.time()) - 600)
        assert not verify_slack_signature(body=b"{}", timestamp=ts, signature=self._sign(b"{}", ts))

    def test_missing_secret_rejects_everything(self, settings):
        settings.SLACK_SIGNING_SECRET = ""
        ts = str(int(time.time()))
        assert not verify_slack_signature(body=b"{}", timestamp=ts, signature=self._sign(b"{}", ts))


# --- Token encryption and OAuth state ---


def test_token_encryption_round_trip():
    encrypted = encrypt_token("xoxb-123")
    assert "xoxb-123" not in encrypted
    assert decrypt_token(encrypted) == "xoxb-123"


class TestOAuthState:
    def test_state_is_single_use(self):
        url = oauth.build_authorize_url(org_id="42", user_id="u1")
        state = parse_qs(urlparse(url).query)["state"][0]

        payload = oauth.consume_state(state)

        assert payload["org"] == "42"
        assert payload["uid"] == "u1"
        assert oauth.consume_state(state) is None

    def test_tampered_state_rejected(self):
        assert oauth.consume_state("not-a-real-state") is None

    def test_authorize_url_contents(self):
        query = parse_qs(urlparse(oauth.build_authorize_url()).query)
        assert query["client_id"] == ["123.456"]
        assert query["redirect_uri"] == ["https://bridge.test/slack/oauth/callback"]
        assert "chat:write" in query["scope"][0].split(",")


# --- Installation service ---


@pytest.mark.django_db
class TestRecordInstallation:
    def test_install_from_one_is_active(self):
        install, claim = record_installation(_oauth_response(), org_id="42", user_id="u1")

        assert claim is None
        assert install.status == InstallationStatus.ACTIVE
        assert install.org_id == "42"
        assert decrypt_token(install.bot_token_encrypted) == "xoxb-secret"
        assert Organization.objects.filter(org_id="42").exists()

    def test_install_from_slack_is_pending_with_claim_code(self):
        install, claim = record_installation(_oauth_response(), org_id=None, user_id=None)

        assert claim
        assert install.status == InstallationStatus.PENDING
        assert install.org_id is None
        assert claim not in install.claim_code_hash

    def test_reinstall_from_slack_keeps_active_org(self):
        record_installation(_oauth_response(), org_id="42", user_id="u1")
        install, claim = record_installation(_oauth_response(token="xoxb-new"), org_id=None, user_id=None)

        assert claim is None
        assert install.status == InstallationStatus.ACTIVE
        assert install.org_id == "42"
        assert decrypt_token(install.bot_token_encrypted) == "xoxb-new"

    def test_other_org_cannot_take_over_active_workspace(self):
        record_installation(_oauth_response(), org_id="42", user_id="u1")
        with pytest.raises(InstallConflictError):
            record_installation(_oauth_response(), org_id="99", user_id="u2")


@pytest.mark.django_db
class TestClaimInstallation:
    def test_claim_links_pending_install(self):
        _, code = record_installation(_oauth_response(), org_id=None, user_id=None)
        install = claim_installation(code, org_id="42", user_id="u1")

        assert install.status == InstallationStatus.ACTIVE
        assert install.org_id == "42"
        assert install.linked_by_user_id == "u1"
        with pytest.raises(InvalidClaimError):
            claim_installation(code, org_id="99", user_id="u2")

    def test_expired_code_rejected(self):
        install, code = record_installation(_oauth_response(), org_id=None, user_id=None)
        install.claim_expires_at = timezone.now() - timedelta(minutes=1)
        install.save()
        with pytest.raises(InvalidClaimError):
            claim_installation(code, org_id="42", user_id="u1")


# --- OAuth callback view ---


@pytest.mark.django_db
class TestOAuthCallbackView:
    def _state(self, **kwargs):
        return parse_qs(urlparse(oauth.build_authorize_url(**kwargs)).query)["state"][0]

    def test_callback_from_one_activates_and_notifies(self):
        state = self._state(org_id="42", user_id="u1")
        with patch.object(oauth, "exchange_code", return_value=_oauth_response()), \
                patch("apps.integrations_slack.views.notify_installer") as notify:
            response = Client().get("/slack/oauth/callback", {"code": "c", "state": state})

        assert response.status_code == 200
        assert b"Slack connected" in response.content
        assert SlackInstallation.objects.get(team_id="T1").status == InstallationStatus.ACTIVE
        notify.assert_called_once()

    def test_callback_from_slack_shows_claim_code(self):
        state = self._state()
        with patch.object(oauth, "exchange_code", return_value=_oauth_response()), \
                patch("apps.integrations_slack.views.notify_installer"):
            response = Client().get("/slack/oauth/callback", {"code": "c", "state": state})

        assert response.status_code == 200
        assert b"Almost done" in response.content
        assert SlackInstallation.objects.get(team_id="T1").status == InstallationStatus.PENDING

    def test_callback_redirects_to_claim_url_when_configured(self, settings):
        settings.SLACK_CLAIM_URL = "https://one.test/slack/link"
        state = self._state()
        with patch.object(oauth, "exchange_code", return_value=_oauth_response()):
            response = Client().get("/slack/oauth/callback", {"code": "c", "state": state})

        assert response.status_code == 302
        assert response["Location"].startswith("https://one.test/slack/link?code=")

    def test_reused_state_rejected(self):
        state = self._state(org_id="42")
        with patch.object(oauth, "exchange_code", return_value=_oauth_response()), \
                patch("apps.integrations_slack.views.notify_installer"):
            Client().get("/slack/oauth/callback", {"code": "c", "state": state})
            response = Client().get("/slack/oauth/callback", {"code": "c", "state": state})

        assert response.status_code == 400

    def test_user_cancelled(self):
        response = Client().get("/slack/oauth/callback", {"error": "access_denied"})
        assert b"cancelled" in response.content

    def test_install_link_redirects_to_slack(self):
        response = Client().get("/slack/install")
        assert response.status_code == 302
        assert response["Location"].startswith(oauth.AUTHORIZE_URL)


# --- Events endpoint ---


@pytest.mark.django_db
class TestEventsView:
    def test_url_verification_challenge(self):
        response = _signed_post(Client(), {"type": "url_verification", "challenge": "abc"})
        assert response.json() == {"challenge": "abc"}

    def test_bad_signature_rejected(self):
        response = _signed_post(Client(), {"type": "url_verification", "challenge": "abc"}, secret="wrong")
        assert response.status_code == 401

    @pytest.mark.parametrize("event_type", ["app_uninstalled", "tokens_revoked"])
    def test_uninstall_deactivates(self, event_type):
        record_installation(_oauth_response(), org_id="42", user_id="u1")
        response = _signed_post(
            Client(), {"type": "event_callback", "team_id": "T1", "event": {"type": event_type}}
        )

        assert response.status_code == 200
        install = SlackInstallation.objects.get(team_id="T1")
        assert install.status == InstallationStatus.INACTIVE
        assert install.deactivated_at is not None

    def test_other_events_acknowledged(self):
        response = _signed_post(
            Client(), {"type": "event_callback", "team_id": "T1", "event": {"type": "message", "text": "hi"}}
        )
        assert response.status_code == 200


# --- Customer API (called from Cyflare ONE) ---


@pytest.mark.django_db
class TestCustomerSlackApi:
    def test_install_url_for_org(self, authenticated_client):
        response = authenticated_client.post("/api/v1/customer/slack/install-url/", {"org_id": "42"}, format="json")

        assert response.status_code == 200
        state = parse_qs(urlparse(response.data["url"]).query)["state"][0]
        assert oauth.consume_state(state)["org"] == "42"

    def test_install_url_rejects_other_org(self, authenticated_client):
        response = authenticated_client.post("/api/v1/customer/slack/install-url/", {"org_id": "99"}, format="json")
        assert response.status_code == 403

    def test_claim_and_list(self, authenticated_client):
        _, code = record_installation(_oauth_response(), org_id=None, user_id=None)
        response = authenticated_client.post(
            "/api/v1/customer/slack/claim/", {"org_id": "42", "code": code}, format="json"
        )
        assert response.status_code == 200
        assert response.data["status"] == "active"

        listing = authenticated_client.get("/api/v1/customer/slack/installations/", {"org_id": "42"})
        assert [i["team_id"] for i in listing.data] == ["T1"]

    def test_bad_claim_code(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/customer/slack/claim/", {"org_id": "42", "code": "nope"}, format="json"
        )
        assert response.status_code == 400

    def test_requires_auth(self, api_client):
        assert api_client.post("/api/v1/customer/slack/install-url/", {}, format="json").status_code in (401, 403)
