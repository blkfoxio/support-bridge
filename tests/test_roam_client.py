"""Tests for the Roam integration client."""

import pytest
import httpx
import respx

from apps.integrations_roam.client import RoamClient
from apps.integrations_roam.exceptions import (
    RoamAuthError,
    RoamNotFoundError,
    RoamRateLimitError,
    RoamServerError,
)
from apps.integrations_roam.mock_client import MockRoamClient


# --- MockRoamClient tests ---

class TestMockRoamClient:
    @pytest.mark.asyncio
    async def test_post_message_records_call(self):
        client = MockRoamClient()
        result = await client.post_message("G-abc123", "Hello", thread_key="conv-uuid")

        assert result.chat == "G-abc123"
        assert result.thread_timestamp is not None
        calls = client.get_calls("post_message")
        assert len(calls) == 1
        assert calls[0].args == ("G-abc123", "Hello")
        assert calls[0].kwargs["thread_key"] == "conv-uuid"

    @pytest.mark.asyncio
    async def test_lookup_user_returns_none(self):
        client = MockRoamClient()
        result = await client.lookup_user("nobody@example.com")
        assert result is None


# --- RoamClient tests with mocked HTTP ---

BASE_URL = "https://api.ro.am/v0"


class TestRoamClientPostMessage:
    @pytest.mark.asyncio
    @respx.mock
    async def test_post_message_success(self):
        respx.post(f"{BASE_URL}/chat.post").mock(
            return_value=httpx.Response(200, json={
                "chat": "C-abc123",
                "threadTimestamp": 1000,
                "timestamp": 1001,
            })
        )

        client = RoamClient(BASE_URL, "test-token")
        result = await client.post_message("G-group1", "Hello world", thread_key="conv-uuid")

        assert result.chat == "C-abc123"
        assert result.thread_timestamp == 1000

        # Verify the request had correct payload
        request = respx.calls[0].request
        import json
        body = json.loads(request.content)
        assert body["chat"] == "G-group1"
        assert body["text"] == "Hello world"
        assert body["threadKey"] == "conv-uuid"
        assert body["markdown"] is True

        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_message_thread_key_truncated_to_64_chars(self):
        respx.post(f"{BASE_URL}/chat.post").mock(
            return_value=httpx.Response(200, json={"chat": "C-abc", "threadTimestamp": 1})
        )

        client = RoamClient(BASE_URL, "test-token")
        long_key = "x" * 100
        await client.post_message("G-group1", "test", thread_key=long_key)

        import json
        body = json.loads(respx.calls[0].request.content)
        assert len(body["threadKey"]) == 64

        await client.close()


class TestRoamClientErrorHandling:
    @pytest.mark.asyncio
    @respx.mock
    async def test_401_raises_auth_error(self):
        respx.post(f"{BASE_URL}/chat.post").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )

        client = RoamClient(BASE_URL, "bad-token")
        with pytest.raises(RoamAuthError) as exc_info:
            await client.post_message("G-group1", "test")
        assert exc_info.value.status_code == 401
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_404_raises_not_found(self):
        respx.get(f"{BASE_URL}/user.lookup").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )

        client = RoamClient(BASE_URL, "test-token")
        result = await client.lookup_user("nobody@example.com")
        assert result is None
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_retries_and_raises(self):
        route = respx.post(f"{BASE_URL}/chat.post").mock(
            return_value=httpx.Response(429, json={"error": "rate limited"})
        )

        client = RoamClient(BASE_URL, "test-token")
        with pytest.raises(RoamRateLimitError):
            await client.post_message("G-group1", "test")

        # Should have retried 3 times
        assert route.call_count == 3
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_500_retries_and_raises(self):
        route = respx.post(f"{BASE_URL}/chat.post").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        client = RoamClient(BASE_URL, "test-token")
        with pytest.raises(RoamServerError):
            await client.post_message("G-group1", "test")

        assert route.call_count == 3
        await client.close()


class TestRoamClientChatHistory:
    @pytest.mark.asyncio
    @respx.mock
    async def test_get_chat_history_parses_messages(self):
        respx.get(f"{BASE_URL}/chat.history").mock(
            return_value=httpx.Response(200, json={
                "chat": "C-abc",
                "messages": [
                    {"id": "msg-1", "text": "Hello", "senderId": "U-user1", "timestamp": 100},
                    {"id": "msg-2", "text": "World", "senderId": "U-user2", "timestamp": 200},
                ],
            })
        )

        client = RoamClient(BASE_URL, "test-token")
        messages = await client.get_chat_history("C-abc")

        assert len(messages) == 2
        assert messages[0].id == "msg-1"
        assert messages[0].text == "Hello"
        assert messages[0].sender_id == "U-user1"
        assert messages[1].text == "World"
        await client.close()


class TestRoamClientTokenInfo:
    @pytest.mark.asyncio
    @respx.mock
    async def test_token_info(self):
        respx.get(f"{BASE_URL}/token.info").mock(
            return_value=httpx.Response(200, json={
                "addr": "B-bot123",
                "scopes": ["chat:post", "chat:history"],
                "roam": {"id": "org-1", "name": "Cyflare", "imageUrl": ""},
            })
        )

        client = RoamClient(BASE_URL, "test-token")
        info = await client.token_info()

        assert info.addr == "B-bot123"
        assert "chat:post" in info.scopes
        assert info.roam_name == "Cyflare"
        await client.close()
