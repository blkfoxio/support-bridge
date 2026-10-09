"""Tests that conversation ownership and org come from the verified token, not the request body."""

import uuid
from unittest.mock import patch

import httpx
import pytest
from django.core.cache import cache

from apps.conversations.models import Conversation
from apps.organizations.models import Organization
from apps.organizations.services import ensure_organization
from apps.queues.factories import QueueFactory
from common.auth import one_org
from common.auth.backends import CognitoUser, FirebaseUser

URL = "/api/v1/customer/conversations/"


def _payload(**overrides):
    data = {
        "org_name": "Acme Corp",
        "customer_name": "Test User",
        "customer_email": "test@acme.com",
        "message": "Need help",
    }
    data.update(overrides)
    return data


def _post(client, data):
    return client.post(URL, data=data, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))


@pytest.fixture
def no_org_client(api_client):
    """Client whose token carries no org claim (current Cognito access tokens)."""
    api_client.force_authenticate(user=CognitoUser(uid="cognito-no-org", email="x@acme.com", claims={}))
    return api_client


@pytest.mark.django_db
class TestCreateConversationIdentity:
    def test_owner_comes_from_token_not_body(self, authenticated_client):
        QueueFactory(key="soc-triage")
        response = _post(authenticated_client, _payload(org_id="42", user_id="someone-else"))

        assert response.status_code == 201
        conv = Conversation.objects.get(id=response.data["conversation"]["id"])
        assert conv.customer_user_id == "test-user-123"

    def test_user_id_may_be_omitted(self, authenticated_client):
        QueueFactory(key="soc-triage")
        response = _post(authenticated_client, _payload(org_id="42"))

        assert response.status_code == 201

    def test_org_mismatch_with_token_claim_is_rejected(self, authenticated_client):
        QueueFactory(key="soc-triage")
        response = _post(authenticated_client, _payload(org_id="99"))

        assert response.status_code == 403
        assert response.data["error"]["code"] == "org_mismatch"
        assert not Conversation.objects.exists()

    def test_token_org_used_when_body_omits_it(self, authenticated_client):
        QueueFactory(key="soc-triage")
        response = _post(authenticated_client, _payload())

        assert response.status_code == 201
        assert response.data["conversation"]["customer_org_id"] == "42"

    def test_body_org_used_when_token_has_no_claim(self, no_org_client):
        QueueFactory(key="soc-triage")
        response = _post(no_org_client, _payload(org_id="77"))

        assert response.status_code == 201
        assert response.data["conversation"]["customer_org_id"] == "77"

    def test_missing_org_everywhere_is_rejected(self, no_org_client):
        QueueFactory(key="soc-triage")
        response = _post(no_org_client, _payload())

        assert response.status_code == 400
        assert response.data["error"]["code"] == "missing_org_id"

    def test_creating_conversation_registers_organization(self, authenticated_client):
        QueueFactory(key="soc-triage")
        _post(authenticated_client, _payload(org_id="42"))

        org = Organization.objects.get(org_id="42")
        assert org.name == "Acme Corp"
        assert org.slack_allow_unlinked_users is True


class TestOrgClaim:
    def test_custom_org_claim_is_read(self):
        assert CognitoUser(uid="u", claims={"custom:org_id": 42}).org_id == "42"

    def test_missing_claim_is_none(self):
        assert FirebaseUser(uid="u", claims={}).org_id is None


@pytest.mark.django_db
class TestEnsureOrganization:
    def test_fills_missing_name_without_overwriting(self):
        ensure_organization("5")
        assert ensure_organization("5", "Beta").name == "Beta"
        assert ensure_organization("5", "Other").name == "Beta"
        assert Organization.objects.count() == 1


# --- Cyflare ONE org verification ---

ONE_URL = "https://one.test"


@pytest.fixture
def one_enabled(settings):
    settings.CYFLARE_ONE_API_BASE_URL = ONE_URL
    cache.clear()
    yield
    cache.clear()


def _one_response(status_code=200, payload=None):
    return httpx.Response(status_code, json=payload or {}, request=httpx.Request("GET", ONE_URL))


@pytest.mark.django_db
class TestCreateConversationWithOneVerification:
    def test_member_org_is_allowed(self, no_org_client, one_enabled):
        QueueFactory(key="soc-triage")
        with patch("common.auth.one_org.user_can_access_org", return_value=True) as check:
            response = _post(no_org_client, _payload(org_id="77"))

        assert response.status_code == 201
        assert check.call_args.kwargs["org_id"] == "77"
        assert check.call_args.kwargs["uid"] == "cognito-no-org"

    def test_non_member_org_is_rejected(self, no_org_client, one_enabled):
        QueueFactory(key="soc-triage")
        with patch("common.auth.one_org.user_can_access_org", return_value=False):
            response = _post(no_org_client, _payload(org_id="77"))

        assert response.status_code == 403
        assert response.data["error"]["code"] == "org_forbidden"
        assert not Conversation.objects.exists()

    def test_one_outage_fails_closed(self, no_org_client, one_enabled):
        QueueFactory(key="soc-triage")
        with patch(
            "common.auth.one_org.user_can_access_org",
            side_effect=one_org.OrgVerificationUnavailableError("timeout"),
        ):
            response = _post(no_org_client, _payload(org_id="77"))

        assert response.status_code == 503
        assert not Conversation.objects.exists()

    def test_verification_skipped_when_not_configured(self, no_org_client, settings):
        settings.CYFLARE_ONE_API_BASE_URL = ""
        QueueFactory(key="soc-triage")
        with patch("common.auth.one_org.user_can_access_org") as check:
            response = _post(no_org_client, _payload(org_id="77"))

        assert response.status_code == 201
        check.assert_not_called()


class TestFetchAccessibleOrgIds:
    def test_collects_ids_across_pages_and_children(self, settings):
        settings.CYFLARE_ONE_API_BASE_URL = ONE_URL
        pages = [
            _one_response(payload={
                "count": 3,
                "next": "more",
                "results": [{"id": 1, "disabled": False, "children": [{"id": 11, "disabled": False}]}],
            }),
            _one_response(payload={
                "count": 3,
                "next": None,
                "results": [{"id": 2, "disabled": True, "children": '[{"id": 21}]'}],
            }),
        ]
        with patch.object(httpx.Client, "get", side_effect=pages):
            assert one_org.fetch_accessible_org_ids("tok") == {"1", "11", "21"}

    def test_rejected_token_means_no_orgs(self, settings):
        settings.CYFLARE_ONE_API_BASE_URL = ONE_URL
        with patch.object(httpx.Client, "get", return_value=_one_response(401)):
            assert one_org.fetch_accessible_org_ids("tok") == set()

    def test_server_error_raises_unavailable(self, settings):
        settings.CYFLARE_ONE_API_BASE_URL = ONE_URL
        with patch.object(httpx.Client, "get", return_value=_one_response(502)):
            with pytest.raises(one_org.OrgVerificationUnavailableError):
                one_org.fetch_accessible_org_ids("tok")

    def test_timeout_raises_unavailable(self, settings):
        settings.CYFLARE_ONE_API_BASE_URL = ONE_URL
        with patch.object(httpx.Client, "get", side_effect=httpx.ReadTimeout("slow")):
            with pytest.raises(one_org.OrgVerificationUnavailableError):
                one_org.fetch_accessible_org_ids("tok")


class TestUserCanAccessOrgCaching:
    def test_result_is_cached(self, one_enabled):
        with patch.object(one_org, "_iter_accessible_org_id_pages", return_value=iter([{"5"}])) as fetch:
            assert one_org.user_can_access_org(token="t", uid="u", org_id="5") is True
            assert one_org.user_can_access_org(token="t", uid="u", org_id="5") is True
        assert fetch.call_count == 1

    def test_stops_paging_once_org_is_found(self, one_enabled):
        first_page = _one_response(payload={"count": 200, "next": "more", "results": [{"id": 5, "disabled": False}]})
        with patch.object(httpx.Client, "get", side_effect=[first_page]) as get:
            assert one_org.user_can_access_org(token="t", uid="u2", org_id="5") is True
        assert get.call_count == 1
