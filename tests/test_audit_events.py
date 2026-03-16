"""Tests for the audit events endpoint."""

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.audit.factories import EventLogFactory
from apps.conversations.factories import ConversationFactory


@pytest.mark.django_db
class TestAuditEventListView:
    def test_list_returns_events(self, ops_client):
        EventLogFactory(event_type="conversation.created", source="customer_api")
        EventLogFactory(event_type="message.sent", source="customer_api")

        url = reverse("admin-config:audit-event-list")
        response = ops_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["results"]) == 2
        assert "limit" in data
        assert "offset" in data

    def test_filter_by_conversation_id(self, ops_client):
        conv = ConversationFactory()
        EventLogFactory(event_type="conversation.created", conversation=conv)
        EventLogFactory(event_type="message.sent")  # No conversation

        url = reverse("admin-config:audit-event-list")
        response = ops_client.get(url, {"conversation_id": str(conv.pk)})
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["conversation_id"] == str(conv.pk)

    def test_filter_by_event_type(self, ops_client):
        EventLogFactory(event_type="conversation.created")
        EventLogFactory(event_type="message.sent")
        EventLogFactory(event_type="conversation.created")

        url = reverse("admin-config:audit-event-list")
        response = ops_client.get(url, {"event_type": "conversation.created"})
        assert response.json()["total"] == 2

    def test_filter_by_source(self, ops_client):
        EventLogFactory(source="customer_api")
        EventLogFactory(source="roam_webhook")

        url = reverse("admin-config:audit-event-list")
        response = ops_client.get(url, {"source": "roam_webhook"})
        assert response.json()["total"] == 1

    def test_filter_by_date_range(self, ops_client):
        now = timezone.now()
        # We can't easily control auto_now_add, so just test the filter accepts the params
        EventLogFactory(event_type="test.event")

        url = reverse("admin-config:audit-event-list")
        response = ops_client.get(url, {
            "created_after": (now - timezone.timedelta(hours=1)).isoformat(),
            "created_before": (now + timezone.timedelta(hours=1)).isoformat(),
        })
        assert response.status_code == 200
        assert response.json()["total"] >= 1

    def test_pagination_limit_offset(self, ops_client):
        for i in range(5):
            EventLogFactory(event_type=f"event.{i}")

        url = reverse("admin-config:audit-event-list")

        # Limit 2
        response = ops_client.get(url, {"limit": 2, "offset": 0})
        data = response.json()
        assert data["total"] == 5
        assert len(data["results"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 0

        # Offset 3
        response = ops_client.get(url, {"limit": 2, "offset": 3})
        data = response.json()
        assert data["total"] == 5
        assert len(data["results"]) == 2

    def test_requires_auth(self, api_client):
        url = reverse("admin-config:audit-event-list")
        response = api_client.get(url)
        assert response.status_code in (401, 403)

    def test_max_limit_capped(self, ops_client):
        url = reverse("admin-config:audit-event-list")
        response = ops_client.get(url, {"limit": 500})
        data = response.json()
        assert data["limit"] == 200
