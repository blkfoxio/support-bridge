"""Tests for the transcript endpoint."""

import uuid

import pytest
from django.urls import reverse

from apps.conversations.factories import (
    AssignmentFactory,
    ConversationFactory,
    ConversationTagFactory,
    TagFactory,
)
from apps.conversations.models import ConversationStatus
from apps.messaging.factories import MessageFactory
from apps.messaging.models import ActorType, MessageDirection, MessageSource
from apps.queues.factories import AnalystProfileFactory, QueueFactory


@pytest.mark.django_db
class TestTranscriptView:
    def test_returns_full_data(self, ops_client):
        queue = QueueFactory(key="transcript-q")
        analyst = AnalystProfileFactory(external_user_id="transcript-analyst")
        conv = ConversationFactory(
            queue=queue,
            status=ConversationStatus.RESOLVED,
            assigned_analyst=analyst,
        )

        # Create messages
        msg1 = MessageFactory(
            conversation=conv,
            actor_type=ActorType.CUSTOMER,
            body_plain="Help me",
            direction=MessageDirection.INBOUND,
            source=MessageSource.CUSTOMER_API,
        )
        msg2 = MessageFactory(
            conversation=conv,
            actor_type=ActorType.ANALYST,
            actor_id=analyst.external_user_id,
            body_plain="On it",
            direction=MessageDirection.OUTBOUND,
            source=MessageSource.ROAM_WEBHOOK,
        )

        # Create assignment
        assignment = AssignmentFactory(conversation=conv, analyst=analyst)

        # Apply tag
        tag = TagFactory(key="resolved-fixed")
        ConversationTagFactory(conversation=conv, tag=tag)

        url = reverse("ops-api:transcript", kwargs={"conversation_id": conv.pk})
        response = ops_client.get(url)
        assert response.status_code == 200

        data = response.json()

        # Conversation metadata
        assert data["conversation"]["id"] == str(conv.pk)
        assert data["conversation"]["queue_key"] == "transcript-q"

        # Messages
        assert len(data["messages"]) == 2
        assert data["messages"][0]["body_plain"] == "Help me"
        assert data["messages"][1]["body_plain"] == "On it"

        # Assignment history
        assert len(data["assignment_history"]) == 1
        assert data["assignment_history"][0]["analyst_id"] == "transcript-analyst"

        # Tags
        assert "resolved-fixed" in data["tags"]

    def test_messages_ordered_by_created_at(self, ops_client):
        conv = ConversationFactory()
        # Create messages — default ordering is by created_at asc
        m1 = MessageFactory(conversation=conv, body_plain="First")
        m2 = MessageFactory(conversation=conv, body_plain="Second")
        m3 = MessageFactory(conversation=conv, body_plain="Third")

        url = reverse("ops-api:transcript", kwargs={"conversation_id": conv.pk})
        response = ops_client.get(url)
        bodies = [m["body_plain"] for m in response.json()["messages"]]
        assert bodies == ["First", "Second", "Third"]

    def test_404_nonexistent(self, ops_client):
        fake_id = uuid.uuid4()
        url = reverse("ops-api:transcript", kwargs={"conversation_id": fake_id})
        response = ops_client.get(url)
        assert response.status_code == 404

    def test_requires_auth(self, api_client):
        conv = ConversationFactory()
        url = reverse("ops-api:transcript", kwargs={"conversation_id": conv.pk})
        response = api_client.get(url)
        assert response.status_code in (401, 403)

    def test_empty_assignment_and_tags(self, ops_client):
        conv = ConversationFactory()
        url = reverse("ops-api:transcript", kwargs={"conversation_id": conv.pk})
        response = ops_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["assignment_history"] == []
        assert data["tags"] == []
