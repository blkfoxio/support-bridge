"""Tests for conversation creation, routing, message sending, and API views."""

import pytest
import uuid

from django.utils import timezone

from apps.conversations.factories import ConversationFactory
from apps.conversations.models import Conversation, ConversationStatus
from apps.conversations.services import ConversationService
from apps.audit.models import EventLog
from apps.integrations_roam.mock_client import MockRoamClient
from apps.messaging.models import Message, ActorType, MessageDirection, MessageSource
from apps.queues.factories import QueueFactory, QueueGroupMappingFactory
from apps.routing.factories import RoutingRuleFactory
from apps.routing.services import RoutingService


# --- Routing Service Tests ---


@pytest.mark.django_db
class TestRoutingService:
    def test_critical_severity_routes_to_incident_response(self):
        incident_queue = QueueFactory(key="incident-response")
        QueueFactory(key="soc-triage")
        RoutingRuleFactory(
            name="Critical → Incident",
            match_json={"field": "severity", "operator": "eq", "value": "critical"},
            target_queue=incident_queue,
            priority=10,
        )

        service = RoutingService()
        result = service.evaluate(org_id="1", tier="standard", issue_category="general", severity="critical")
        assert result.key == "incident-response"

    def test_billing_category_routes_to_billing_support(self):
        billing_queue = QueueFactory(key="billing-support")
        QueueFactory(key="soc-triage")
        RoutingRuleFactory(
            name="Billing → Billing Support",
            match_json={"field": "issue_category", "operator": "eq", "value": "billing"},
            target_queue=billing_queue,
            priority=20,
        )

        service = RoutingService()
        result = service.evaluate(org_id="1", tier="standard", issue_category="billing", severity="medium")
        assert result.key == "billing-support"

    def test_enterprise_tier_routes_to_enterprise_soc(self):
        enterprise_queue = QueueFactory(key="enterprise-soc")
        QueueFactory(key="soc-triage")
        RoutingRuleFactory(
            name="Enterprise → Enterprise SOC",
            match_json={"field": "tier", "operator": "eq", "value": "enterprise"},
            target_queue=enterprise_queue,
            priority=30,
        )

        service = RoutingService()
        result = service.evaluate(org_id="1", tier="enterprise", issue_category="general", severity="medium")
        assert result.key == "enterprise-soc"

    def test_no_matching_rule_falls_back_to_soc_triage(self):
        QueueFactory(key="soc-triage")

        service = RoutingService()
        result = service.evaluate(org_id="1", tier="standard", issue_category="general", severity="low")
        assert result.key == "soc-triage"

    def test_highest_priority_rule_wins(self):
        """Lower priority number = higher priority. If both match, first wins."""
        incident_queue = QueueFactory(key="incident-response")
        enterprise_queue = QueueFactory(key="enterprise-soc")
        QueueFactory(key="soc-triage")

        RoutingRuleFactory(
            name="Critical",
            match_json={"field": "severity", "operator": "eq", "value": "critical"},
            target_queue=incident_queue,
            priority=10,
        )
        RoutingRuleFactory(
            name="Enterprise",
            match_json={"field": "tier", "operator": "eq", "value": "enterprise"},
            target_queue=enterprise_queue,
            priority=30,
        )

        service = RoutingService()
        result = service.evaluate(org_id="1", tier="enterprise", issue_category="general", severity="critical")
        assert result.key == "incident-response"

    def test_inactive_rules_are_skipped(self):
        incident_queue = QueueFactory(key="incident-response")
        QueueFactory(key="soc-triage")
        RoutingRuleFactory(
            match_json={"field": "severity", "operator": "eq", "value": "critical"},
            target_queue=incident_queue,
            priority=10,
            active=False,
        )

        service = RoutingService()
        result = service.evaluate(org_id="1", tier="standard", issue_category="general", severity="critical")
        assert result.key == "soc-triage"

    def test_in_operator(self):
        enterprise_queue = QueueFactory(key="enterprise-soc")
        QueueFactory(key="soc-triage")
        RoutingRuleFactory(
            match_json={"field": "tier", "operator": "in", "value": ["enterprise", "premium"]},
            target_queue=enterprise_queue,
            priority=10,
        )

        service = RoutingService()
        result = service.evaluate(org_id="1", tier="enterprise", issue_category="general", severity="medium")
        assert result.key == "enterprise-soc"

    def test_unknown_operator_does_not_match(self):
        some_queue = QueueFactory(key="some-queue")
        QueueFactory(key="soc-triage")
        RoutingRuleFactory(
            match_json={"field": "tier", "operator": "regex", "value": ".*"},
            target_queue=some_queue,
            priority=10,
        )

        service = RoutingService()
        result = service.evaluate(org_id="1", tier="enterprise", issue_category="general", severity="medium")
        assert result.key == "soc-triage"


# --- Conversation Service Tests ---


@pytest.mark.django_db
class TestConversationServiceCreate:
    def setup_method(self):
        self.queue = QueueFactory(key="soc-triage")
        self.mapping = QueueGroupMappingFactory(queue=self.queue, roam_group_id="G-test-group")
        self.mock_client = MockRoamClient()
        self.service = ConversationService(self.mock_client)

    def test_create_conversation_happy_path(self):
        conversation, message = self.service.create_conversation(
            org_id="42",
            org_name="Acme Corp",
            user_id="user-123",
            customer_name="Jane Smith",
            customer_email="jane@acme.com",
            tier="standard",
            issue_category="general",
            severity="medium",
            source_channel="mobile_ios",
            message_body="Help me please",
            idempotency_key=str(uuid.uuid4()),
        )

        assert conversation.customer_org_id == "42"
        assert conversation.customer_org_name == "Acme Corp"
        assert conversation.customer_name == "Jane Smith"
        assert conversation.customer_email == "jane@acme.com"
        assert conversation.status == ConversationStatus.QUEUED
        assert conversation.queue.key == "soc-triage"
        assert conversation.roam_thread_key == str(conversation.id)

        assert message.body_plain == "Help me please"
        assert message.actor_type == ActorType.CUSTOMER
        assert message.direction == MessageDirection.INBOUND
        assert message.source == MessageSource.CUSTOMER_API
        assert message.delivered_at is not None

    def test_create_conversation_posts_blocks_to_roam(self):
        self.service.create_conversation(
            org_id="42",
            org_name="Acme Corp",
            user_id="user-123",
            customer_name="Jane Smith",
            customer_email="jane@acme.com",
            tier="standard",
            issue_category="general",
            severity="medium",
            source_channel="mobile_ios",
            message_body="Help me please",
            idempotency_key=str(uuid.uuid4()),
        )

        # Root message now uses post_blocks (Block Kit), not post_message
        assert len(self.mock_client.get_calls("post_message")) == 0
        calls = self.mock_client.get_calls("post_blocks")
        assert len(calls) == 1
        assert calls[0].args[0] == "G-test-group"  # chat_id
        blocks = calls[0].args[1]
        assert isinstance(blocks, list)
        assert len(blocks) <= 10
        # Verify color is set
        assert calls[0].kwargs.get("color") is not None

    def test_create_conversation_records_event_log(self):
        idem_key = str(uuid.uuid4())
        self.service.create_conversation(
            org_id="42",
            org_name="Acme Corp",
            user_id="user-123",
            customer_name="Jane Smith",
            customer_email="jane@acme.com",
            tier="standard",
            issue_category="general",
            severity="medium",
            source_channel="mobile_ios",
            message_body="Help",
            idempotency_key=idem_key,
        )

        event = EventLog.objects.get(idempotency_key=idem_key)
        assert event.event_type == "conversation.created"
        assert event.source == "customer_api"

    def test_idempotency_returns_existing_conversation(self):
        idem_key = str(uuid.uuid4())
        kwargs = dict(
            org_id="42",
            org_name="Acme Corp",
            user_id="user-123",
            customer_name="Jane Smith",
            customer_email="jane@acme.com",
            tier="standard",
            issue_category="general",
            severity="medium",
            source_channel="mobile_ios",
            message_body="Help",
            idempotency_key=idem_key,
        )

        conv1, msg1 = self.service.create_conversation(**kwargs)
        conv2, msg2 = self.service.create_conversation(**kwargs)

        assert conv1.id == conv2.id
        assert Conversation.objects.count() == 1

    def test_create_conversation_routes_critical_to_incident(self):
        incident_queue = QueueFactory(key="incident-response")
        QueueGroupMappingFactory(queue=incident_queue, roam_group_id="G-incident")
        RoutingRuleFactory(
            match_json={"field": "severity", "operator": "eq", "value": "critical"},
            target_queue=incident_queue,
            priority=10,
        )

        conversation, _ = self.service.create_conversation(
            org_id="42",
            org_name="Acme Corp",
            user_id="user-123",
            customer_name="Jane Smith",
            customer_email="jane@acme.com",
            tier="standard",
            issue_category="general",
            severity="critical",
            source_channel="mobile_ios",
            message_body="Critical incident!",
            idempotency_key=str(uuid.uuid4()),
        )

        assert conversation.queue.key == "incident-response"

    def test_no_roam_mapping_still_creates_conversation(self):
        """When no QueueGroupMapping exists, conversation is created but nothing posted to Roam."""
        no_mapping_queue = QueueFactory(key="no-mapping-queue")
        RoutingRuleFactory(
            match_json={"field": "tier", "operator": "eq", "value": "no-mapping"},
            target_queue=no_mapping_queue,
            priority=5,
        )

        conversation, message = self.service.create_conversation(
            org_id="42",
            org_name="Acme Corp",
            user_id="user-123",
            customer_name="Jane Smith",
            customer_email="jane@acme.com",
            tier="no-mapping",
            issue_category="general",
            severity="medium",
            source_channel="mobile_ios",
            message_body="Help",
            idempotency_key=str(uuid.uuid4()),
        )

        assert conversation.id is not None
        assert message.delivered_at is None
        assert len(self.mock_client.get_calls("post_blocks")) == 0
        assert len(self.mock_client.get_calls("post_message")) == 0


@pytest.mark.django_db
class TestConversationServiceSendMessage:
    def setup_method(self):
        self.queue = QueueFactory(key="soc-triage")
        self.mapping = QueueGroupMappingFactory(queue=self.queue, roam_group_id="G-test-group")
        self.mock_client = MockRoamClient()
        self.service = ConversationService(self.mock_client)

    def test_send_message_happy_path(self):
        conversation = ConversationFactory(
            customer_user_id="user-123",
            queue=self.queue,
            status=ConversationStatus.ASSIGNED,
        )

        message = self.service.send_message(
            conversation_id=str(conversation.id),
            user_id="user-123",
            body="Follow-up message",
            idempotency_key=str(uuid.uuid4()),
        )

        assert message.body_plain == "Follow-up message"
        assert message.actor_type == ActorType.CUSTOMER
        assert message.conversation_id == conversation.id

    def test_send_message_updates_last_message_at(self):
        conversation = ConversationFactory(
            customer_user_id="user-123",
            queue=self.queue,
        )
        before = timezone.now()

        self.service.send_message(
            conversation_id=str(conversation.id),
            user_id="user-123",
            body="Update",
            idempotency_key=str(uuid.uuid4()),
        )

        conversation.refresh_from_db()
        assert conversation.last_message_at is not None
        assert conversation.last_message_at >= before

    def test_send_message_transitions_waiting_customer_to_waiting_soc(self):
        conversation = ConversationFactory(
            customer_user_id="user-123",
            queue=self.queue,
            status=ConversationStatus.WAITING_CUSTOMER,
        )

        self.service.send_message(
            conversation_id=str(conversation.id),
            user_id="user-123",
            body="Responding",
            idempotency_key=str(uuid.uuid4()),
        )

        conversation.refresh_from_db()
        assert conversation.status == ConversationStatus.WAITING_SOC

    def test_send_message_wrong_user_raises_permission_error(self):
        conversation = ConversationFactory(
            customer_user_id="user-123",
            queue=self.queue,
        )

        with pytest.raises(PermissionError, match="does not own"):
            self.service.send_message(
                conversation_id=str(conversation.id),
                user_id="wrong-user",
                body="Hacking attempt",
                idempotency_key=str(uuid.uuid4()),
            )

    def test_send_message_to_closed_conversation_raises_value_error(self):
        conversation = ConversationFactory(
            customer_user_id="user-123",
            queue=self.queue,
            status=ConversationStatus.CLOSED,
        )

        with pytest.raises(ValueError, match="closed conversation"):
            self.service.send_message(
                conversation_id=str(conversation.id),
                user_id="user-123",
                body="Too late",
                idempotency_key=str(uuid.uuid4()),
            )

    def test_send_message_posts_to_roam(self):
        conversation = ConversationFactory(
            customer_user_id="user-123",
            customer_name="Jane Smith",
            customer_org_name="Acme Corp",
            queue=self.queue,
        )

        self.service.send_message(
            conversation_id=str(conversation.id),
            user_id="user-123",
            body="Follow-up",
            idempotency_key=str(uuid.uuid4()),
        )

        calls = self.mock_client.get_calls("post_message")
        assert len(calls) == 1
        assert "Jane Smith" in calls[0].args[1]
        assert "Follow-up" in calls[0].args[1]

    def test_send_message_idempotency(self):
        conversation = ConversationFactory(
            customer_user_id="user-123",
            queue=self.queue,
        )
        idem_key = str(uuid.uuid4())

        msg1 = self.service.send_message(
            conversation_id=str(conversation.id),
            user_id="user-123",
            body="Hello",
            idempotency_key=idem_key,
        )
        msg2 = self.service.send_message(
            conversation_id=str(conversation.id),
            user_id="user-123",
            body="Hello",
            idempotency_key=idem_key,
        )

        assert msg1.id == msg2.id
        assert Message.objects.filter(conversation=conversation).count() == 1


# --- Customer API View Tests ---


@pytest.mark.django_db
class TestCreateConversationAPI:
    def test_create_conversation_returns_201(self, authenticated_client):
        QueueFactory(key="soc-triage")

        response = authenticated_client.post(
            "/api/v1/customer/conversations/",
            data={
                "org_id": "42",
                "org_name": "Acme Corp",
                "user_id": "test-user-123",
                "customer_name": "Test User",
                "customer_email": "test@acme.com",
                "message": "Need help",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        assert response.status_code == 201
        assert "conversation" in response.data
        assert "message" in response.data
        assert response.data["conversation"]["customer_org_id"] == "42"

    def test_create_conversation_missing_idempotency_key(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/customer/conversations/",
            data={
                "org_id": "42",
                "org_name": "Acme Corp",
                "user_id": "test-user-123",
                "customer_name": "Test User",
                "customer_email": "test@acme.com",
                "message": "Need help",
            },
            format="json",
        )

        assert response.status_code == 400
        assert "idempotency" in response.data["error"]["message"].lower()

    def test_create_conversation_unauthenticated(self, api_client):
        response = api_client.post(
            "/api/v1/customer/conversations/",
            data={"org_id": "42", "message": "test"},
            format="json",
        )

        assert response.status_code in (401, 403)

    def test_create_conversation_invalid_data(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/customer/conversations/",
            data={},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        assert response.status_code == 400


@pytest.mark.django_db
class TestConversationDetailAPI:
    def test_get_own_conversation(self, authenticated_client):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(
            customer_user_id="test-user-123",
            queue=queue,
        )

        response = authenticated_client.get(f"/api/v1/customer/conversations/{conversation.id}/")

        assert response.status_code == 200
        assert response.data["id"] == str(conversation.id)

    def test_get_other_users_conversation_returns_403(self, authenticated_client):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(
            customer_user_id="other-user",
            queue=queue,
        )

        response = authenticated_client.get(f"/api/v1/customer/conversations/{conversation.id}/")

        assert response.status_code == 403

    def test_get_nonexistent_conversation_returns_404(self, authenticated_client):
        fake_id = uuid.uuid4()
        response = authenticated_client.get(f"/api/v1/customer/conversations/{fake_id}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestConversationMessagesAPI:
    def test_list_messages(self, authenticated_client):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(
            customer_user_id="test-user-123",
            queue=queue,
        )
        Message.objects.create(
            conversation=conversation,
            actor_type=ActorType.CUSTOMER,
            actor_id="test-user-123",
            direction=MessageDirection.INBOUND,
            source=MessageSource.CUSTOMER_API,
            body_plain="Hello",
        )

        response = authenticated_client.get(f"/api/v1/customer/conversations/{conversation.id}/messages/")

        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["body_plain"] == "Hello"

    def test_send_message_returns_201(self, authenticated_client):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(
            customer_user_id="test-user-123",
            queue=queue,
        )

        response = authenticated_client.post(
            f"/api/v1/customer/conversations/{conversation.id}/messages/",
            data={"message": "Follow-up"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        assert response.status_code == 201
        assert response.data["body_plain"] == "Follow-up"

    def test_send_message_to_other_users_conversation_returns_403(self, authenticated_client):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(
            customer_user_id="other-user",
            queue=queue,
        )

        response = authenticated_client.post(
            f"/api/v1/customer/conversations/{conversation.id}/messages/",
            data={"message": "Nope"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        assert response.status_code == 403
