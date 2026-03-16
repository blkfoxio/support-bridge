"""Tests for SSE pub/sub infrastructure and streaming endpoint (Task 7)."""

import json
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.sse.service import SSEEvent, SSEPublisher, _channel_name


# --- SSEEvent Tests ---


class TestSSEEvent:
    def test_event_has_defaults(self):
        event = SSEEvent(event_type="message.created")
        assert event.event_type == "message.created"
        assert event.event_id.startswith("evt_")
        assert event.timestamp != ""
        assert event.data == {}

    def test_event_with_data(self):
        data = {"message_id": "abc-123", "body": "Hello"}
        event = SSEEvent(event_type="message.created", data=data)
        assert event.data == data

    def test_to_sse_format(self):
        event = SSEEvent(
            event_type="message.created",
            event_id="evt_test123",
            data={"key": "value"},
        )
        sse_text = event.to_sse()
        assert "event: message.created\n" in sse_text
        assert "id: evt_test123\n" in sse_text
        assert 'data: {"key": "value"}\n' in sse_text
        # Must end with double newline for SSE spec
        assert sse_text.endswith("\n\n")

    def test_to_sse_empty_data(self):
        event = SSEEvent(event_type="heartbeat", event_id="evt_hb1", data={})
        sse_text = event.to_sse()
        assert "data: {}\n" in sse_text

    def test_event_serializable(self):
        event = SSEEvent(event_type="test", data={"nested": {"key": "val"}})
        serialized = json.dumps(asdict(event))
        parsed = json.loads(serialized)
        assert parsed["event_type"] == "test"
        assert parsed["data"]["nested"]["key"] == "val"


# --- Channel Name Tests ---


class TestChannelName:
    def test_channel_format(self):
        assert _channel_name("abc-123") == "conversation:abc-123"

    def test_channel_with_uuid(self):
        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        assert _channel_name(uuid_str) == f"conversation:{uuid_str}"


# --- SSEPublisher Tests ---


class TestSSEPublisher:
    @patch("common.sse.service.redis.Redis.from_url")
    def test_publish_calls_redis(self, mock_from_url):
        mock_redis = MagicMock()
        mock_from_url.return_value = mock_redis

        publisher = SSEPublisher()
        event_id = publisher.publish(
            conversation_id="conv-123",
            event_type="message.created",
            data={"body": "Hello"},
        )

        assert event_id.startswith("evt_")
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "conversation:conv-123"

        # Verify the published payload is valid JSON with expected structure
        payload = json.loads(call_args[0][1])
        assert payload["event_type"] == "message.created"
        assert payload["data"]["body"] == "Hello"
        assert payload["event_id"] == event_id

    @patch("common.sse.service.redis.Redis.from_url")
    def test_publish_returns_unique_event_ids(self, mock_from_url):
        mock_from_url.return_value = MagicMock()

        publisher = SSEPublisher()
        id1 = publisher.publish("conv-1", "test", {})
        id2 = publisher.publish("conv-1", "test", {})
        assert id1 != id2


# --- SSE Streaming Endpoint Tests ---


@pytest.mark.django_db
class TestCustomerSSEStreamAuth:
    """Test authentication and authorization for the SSE endpoint."""

    @pytest.mark.asyncio
    async def test_rejects_non_get(self):
        """SSE endpoint should reject POST requests."""
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.post("/api/v1/customer/stream/")

        from apps.customer_api.stream_views import customer_sse_stream

        response = await customer_sse_stream(request)
        assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_rejects_missing_auth(self):
        """SSE endpoint should reject requests without Authorization header."""
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/api/v1/customer/stream/?conversation_id=abc")

        from apps.customer_api.stream_views import customer_sse_stream

        response = await customer_sse_stream(request)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_invalid_token(self):
        """SSE endpoint should reject requests with invalid Bearer token."""
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(
            "/api/v1/customer/stream/?conversation_id=abc",
            HTTP_AUTHORIZATION="Bearer invalid-token",
        )

        with patch(
            "apps.customer_api.stream_views._verify_firebase_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from apps.customer_api.stream_views import customer_sse_stream

            response = await customer_sse_stream(request)
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_missing_conversation_id(self):
        """SSE endpoint should reject requests without conversation_id param."""
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(
            "/api/v1/customer/stream/",
            HTTP_AUTHORIZATION="Bearer valid-token",
        )

        with patch(
            "apps.customer_api.stream_views._verify_firebase_token",
            new_callable=AsyncMock,
            return_value={"uid": "user-123"},
        ):
            from apps.customer_api.stream_views import customer_sse_stream

            response = await customer_sse_stream(request)
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_nonexistent_conversation(self):
        """SSE endpoint should return 404 for nonexistent conversation."""
        import uuid

        from django.test import RequestFactory

        factory = RequestFactory()
        fake_id = str(uuid.uuid4())
        request = factory.get(
            f"/api/v1/customer/stream/?conversation_id={fake_id}",
            HTTP_AUTHORIZATION="Bearer valid-token",
        )

        with patch(
            "apps.customer_api.stream_views._verify_firebase_token",
            new_callable=AsyncMock,
            return_value={"uid": "user-123"},
        ):
            from apps.customer_api.stream_views import customer_sse_stream

            response = await customer_sse_stream(request)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_unauthorized_conversation(self):
        """SSE endpoint should return 403 when user doesn't own the conversation."""
        from asgiref.sync import sync_to_async
        from django.test import RequestFactory

        from apps.conversations.factories import ConversationFactory
        from apps.queues.factories import QueueFactory

        queue = await sync_to_async(QueueFactory)(key="soc-triage")
        conversation = await sync_to_async(ConversationFactory)(
            queue=queue,
            customer_user_id="other-user-456",
        )

        factory = RequestFactory()
        request = factory.get(
            f"/api/v1/customer/stream/?conversation_id={conversation.id}",
            HTTP_AUTHORIZATION="Bearer valid-token",
        )

        with patch(
            "apps.customer_api.stream_views._verify_firebase_token",
            new_callable=AsyncMock,
            return_value={"uid": "requesting-user-123"},
        ):
            from apps.customer_api.stream_views import customer_sse_stream

            response = await customer_sse_stream(request)
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_streaming_response_for_owner(self):
        """SSE endpoint should return StreamingHttpResponse for valid owner."""
        from asgiref.sync import sync_to_async
        from django.http import StreamingHttpResponse
        from django.test import RequestFactory

        from apps.conversations.factories import ConversationFactory
        from apps.queues.factories import QueueFactory

        queue = await sync_to_async(QueueFactory)(key="soc-triage")
        conversation = await sync_to_async(ConversationFactory)(
            queue=queue,
            customer_user_id="owner-user-789",
        )

        factory = RequestFactory()
        request = factory.get(
            f"/api/v1/customer/stream/?conversation_id={conversation.id}",
            HTTP_AUTHORIZATION="Bearer valid-token",
        )

        with patch(
            "apps.customer_api.stream_views._verify_firebase_token",
            new_callable=AsyncMock,
            return_value={"uid": "owner-user-789"},
        ):
            from apps.customer_api.stream_views import customer_sse_stream

            response = await customer_sse_stream(request)
            assert isinstance(response, StreamingHttpResponse)
            assert response["Content-Type"] == "text/event-stream"
            assert response["Cache-Control"] == "no-cache"
            assert response["X-Accel-Buffering"] == "no"


# --- Heartbeat Format Test ---


class TestHeartbeatFormat:
    def test_heartbeat_event_format(self):
        from apps.customer_api.stream_views import _heartbeat_sse

        heartbeat = _heartbeat_sse()
        assert "event: heartbeat" in heartbeat
        assert '"type": "ping"' in heartbeat
        assert heartbeat.endswith("\n\n")
