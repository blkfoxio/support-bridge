"""Tests for conversation participants and external identity linking."""

import pytest

from apps.conversations.access import accessible_conversations, can_access
from apps.conversations.factories import ConversationFactory
from apps.conversations.models import ConversationParticipant, Feedback, ParticipantRole
from apps.conversations.services import ConversationService
from apps.identities.services import auto_link_by_email, link_identity, upsert_identity
from apps.integrations_roam.mock_client import MockRoamClient
from apps.messaging.factories import MessageFactory
from apps.messaging.models import ActorType
from apps.queues.factories import QueueFactory


@pytest.fixture
def queue(db):
    return QueueFactory(key="soc-triage")


def _slack_identity(user="U1", email="jane@acme.com", org="42"):
    return upsert_identity(
        provider="slack", team_id="T1", external_user_id=user, org_id=org, email=email, display_name="Jane"
    )


@pytest.mark.django_db
class TestAccess:
    def test_owner_and_participant_have_access(self, queue):
        conv = ConversationFactory(queue=queue, customer_user_id="owner")
        ConversationParticipant.objects.create(conversation=conv, user_id="bob")

        assert can_access(conv, "owner")
        assert can_access(conv, "bob")
        assert not can_access(conv, "mallory")

    def test_accessible_conversations_lists_owned_and_participating(self, queue):
        owned = ConversationFactory(queue=queue, customer_user_id="bob")
        shared = ConversationFactory(queue=queue, customer_user_id="owner")
        ConversationParticipant.objects.create(conversation=shared, user_id="bob")
        ConversationFactory(queue=queue, customer_user_id="someone-else")

        assert set(accessible_conversations("bob")) == {owned, shared}

    def test_create_conversation_registers_owner_participant(self, queue):
        conv, _ = ConversationService(MockRoamClient()).create_conversation(
            org_id="42", org_name="Acme", user_id="u1", customer_name="U", customer_email="u@acme.com",
            tier="standard", issue_category="general", severity="medium", source_channel="web",
            message_body="hi", idempotency_key="k-1",
        )
        assert conv.participants.get().role == ParticipantRole.OWNER

    def test_participant_can_send_message(self, queue):
        conv = ConversationFactory(queue=queue, customer_user_id="owner")
        ConversationParticipant.objects.create(conversation=conv, user_id="bob")

        msg = ConversationService(MockRoamClient()).send_message(
            conversation_id=conv.id, user_id="bob", body="me too", idempotency_key="k-2"
        )
        assert msg.actor_id == "bob"


@pytest.mark.django_db
class TestCustomerApiWithParticipants:
    def test_participant_sees_conversation_in_list_and_detail(self, authenticated_client, queue):
        conv = ConversationFactory(queue=queue, customer_user_id="someone-else")
        ConversationParticipant.objects.create(conversation=conv, user_id="test-user-123")

        listing = authenticated_client.get("/api/v1/customer/conversations/")
        detail = authenticated_client.get(f"/api/v1/customer/conversations/{conv.id}/")

        assert [c["id"] for c in listing.data] == [str(conv.id)]
        assert detail.status_code == 200

    def test_non_participant_forbidden(self, authenticated_client, queue):
        conv = ConversationFactory(queue=queue, customer_user_id="someone-else")
        assert authenticated_client.get(f"/api/v1/customer/conversations/{conv.id}/").status_code == 403


@pytest.mark.django_db
class TestIdentityLinking:
    def test_upsert_refreshes_profile(self):
        _slack_identity(email="old@acme.com")
        identity = _slack_identity(email="new@acme.com")
        assert identity.email == "new@acme.com"
        assert identity.synthetic_user_id == "slack:T1:U1"
        assert identity.effective_user_id == "slack:T1:U1"

    def test_link_moves_history_to_real_user(self, queue):
        identity = _slack_identity()
        synthetic = identity.synthetic_user_id
        owned = ConversationFactory(queue=queue, customer_user_id=synthetic)
        ConversationParticipant.objects.create(conversation=owned, user_id=synthetic, role=ParticipantRole.OWNER)
        shared = ConversationFactory(queue=queue, customer_user_id="other")
        ConversationParticipant.objects.create(conversation=shared, user_id=synthetic, identity=identity)
        MessageFactory(conversation=owned, actor_type=ActorType.CUSTOMER, actor_id=synthetic)
        Feedback.objects.create(conversation=owned, customer_user_id=synthetic, rating=3)

        assert link_identity(identity, "one-user") == 1

        owned.refresh_from_db()
        assert owned.customer_user_id == "one-user"
        assert set(accessible_conversations("one-user")) == {owned, shared}
        assert not ConversationParticipant.objects.filter(user_id=synthetic).exists()
        assert owned.messages.get().actor_id == "one-user"
        assert Feedback.objects.get().customer_user_id == "one-user"
        identity.refresh_from_db()
        assert identity.effective_user_id == "one-user"

    def test_link_deduplicates_existing_participation(self, queue):
        identity = _slack_identity()
        conv = ConversationFactory(queue=queue, customer_user_id="other")
        ConversationParticipant.objects.create(conversation=conv, user_id=identity.synthetic_user_id)
        ConversationParticipant.objects.create(conversation=conv, user_id="one-user")

        link_identity(identity, "one-user")

        assert list(conv.participants.values_list("user_id", flat=True)) == ["one-user"]

    def test_auto_link_by_email_only_within_org(self):
        same_org = _slack_identity(user="U1", email="Jane@Acme.com", org="42")
        other_org = _slack_identity(user="U2", email="jane@acme.com", org="99")

        linked = auto_link_by_email(user_id="one-user", email="jane@acme.com", org_id="42")

        assert linked == [same_org]
        other_org.refresh_from_db()
        assert other_org.linked_user_id is None
