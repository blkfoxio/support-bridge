"""Roam Chat API v0 client.

Base URL: https://api.ro.am/v0
Auth: Bearer token
IDs: Tagged UUIDs with prefixes (U-, C-, G-, D-, B-)
Pagination: Cursor-based
Thread support: threadKey (string, max 64 chars) for external identifiers
"""

import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .exceptions import (
    RoamApiError,
    RoamAuthError,
    RoamNotFoundError,
    RoamRateLimitError,
    RoamServerError,
)
from .types import (
    RoamChat,
    RoamGroup,
    RoamMessage,
    RoamPostResponse,
    RoamTokenInfo,
    RoamUser,
)

logger = logging.getLogger(__name__)


def _raise_for_status(response: httpx.Response) -> None:
    """Map HTTP status codes to typed exceptions."""
    if response.is_success:
        return

    body = response.text
    status = response.status_code

    if status in (401, 403):
        raise RoamAuthError(f"Authentication failed: {status}", status_code=status, response_body=body)
    elif status == 404:
        raise RoamNotFoundError(f"Resource not found: {status}", status_code=status, response_body=body)
    elif status == 429:
        raise RoamRateLimitError(f"Rate limit exceeded: {status}", status_code=status, response_body=body)
    elif status >= 500:
        raise RoamServerError(f"Roam server error: {status}", status_code=status, response_body=body)
    else:
        raise RoamApiError(f"Roam API error: {status}", status_code=status, response_body=body)


class RoamClient:
    """HTTP client for the Roam Chat API v0."""

    def __init__(self, base_url: str, token: str, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    # -- Chat & Messaging --

    @retry(
        retry=retry_if_exception_type((RoamRateLimitError, RoamServerError)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def post_message(
        self, chat_id: str, text: str, *, thread_key: str | None = None, markdown: bool = True
    ) -> RoamPostResponse:
        """Post a message via /chat.post.

        Args:
            chat_id: Tagged UUID of the chat/group (C-... or G-...).
            text: Message text (supports markdown).
            thread_key: External thread identifier (max 64 chars). Mutually exclusive with threadTimestamp.
            markdown: Whether to parse text as markdown (default True).
        """
        payload: dict = {"chat": chat_id, "text": text, "markdown": markdown}
        if thread_key is not None:
            payload["threadKey"] = thread_key[:64]

        response = await self._client.post("/chat.post", json=payload)
        _raise_for_status(response)
        data = response.json()

        return RoamPostResponse(
            chat=data.get("chat", ""),
            thread_timestamp=data.get("threadTimestamp"),
            timestamp=data.get("timestamp"),
            raw=data,
        )

    @retry(
        retry=retry_if_exception_type((RoamRateLimitError, RoamServerError)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def post_blocks(
        self, chat_id: str, blocks: list[dict], *, color: str | None = None, thread_key: str | None = None
    ) -> RoamPostResponse:
        """Post a Block Kit message via /chat.post.

        Args:
            chat_id: Tagged UUID of the chat/group (C-... or G-...).
            blocks: List of block objects (max 10). Mutually exclusive with text.
            color: Left-strip color — "good", "warning", "danger", or "#RRGGBB".
            thread_key: External thread identifier (max 64 chars).
        """
        payload: dict = {"chat": chat_id, "blocks": blocks}
        if color is not None:
            payload["color"] = color
        if thread_key is not None:
            payload["threadKey"] = thread_key[:64]

        response = await self._client.post("/chat.post", json=payload)
        _raise_for_status(response)
        data = response.json()

        return RoamPostResponse(
            chat=data.get("chat", ""),
            thread_timestamp=data.get("threadTimestamp"),
            timestamp=data.get("timestamp"),
            raw=data,
        )

    @retry(
        retry=retry_if_exception_type((RoamRateLimitError, RoamServerError)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def get_chat_history(
        self, chat_id: str, *, thread_timestamp: int | None = None, limit: int = 50
    ) -> list[RoamMessage]:
        """Get message history via /chat.history.

        Args:
            chat_id: Tagged UUID of the chat.
            thread_timestamp: Filter to a specific thread.
            limit: Max messages to return (1-200, default 50).
        """
        params: dict = {"chat": chat_id, "limit": min(limit, 200)}
        if thread_timestamp is not None:
            params["threadTimestamp"] = thread_timestamp

        response = await self._client.get("/chat.history", params=params)
        _raise_for_status(response)
        data = response.json()

        messages = []
        for msg in data.get("messages", []):
            messages.append(RoamMessage(
                id=msg.get("id", ""),
                text=msg.get("text", ""),
                sender_id=msg.get("senderId", msg.get("sender", "")),
                sender_name=msg.get("senderName", ""),
                thread_key=msg.get("threadKey"),
                thread_timestamp=msg.get("threadTimestamp"),
                timestamp=msg.get("timestamp"),
                raw=msg,
            ))
        return messages

    @retry(
        retry=retry_if_exception_type((RoamRateLimitError, RoamServerError)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def list_chats(self, *, limit: int = 100) -> list[RoamChat]:
        """List accessible chats via /chat.list."""
        params = {"limit": min(limit, 100)}
        response = await self._client.get("/chat.list", params=params)
        _raise_for_status(response)
        data = response.json()

        return [
            RoamChat(
                id=chat.get("id", ""),
                name=chat.get("name", ""),
                group=chat.get("group"),
                started=chat.get("started", ""),
                raw=chat,
            )
            for chat in data.get("chats", [])
        ]

    async def send_typing(self, chat_id: str, *, thread_timestamp: int | None = None) -> None:
        """Show typing indicator via /chat.typing."""
        payload: dict = {"chat": chat_id}
        if thread_timestamp is not None:
            payload["threadTimestamp"] = thread_timestamp
        response = await self._client.post("/chat.typing", json=payload)
        _raise_for_status(response)

    # -- Groups --

    @retry(
        retry=retry_if_exception_type((RoamRateLimitError, RoamServerError)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def create_group(self, name: str, *, private: bool = True) -> RoamGroup:
        """Create a new group via /group.create."""
        payload = {"name": name[:64], "private": private}
        response = await self._client.post("/group.create", json=payload)
        _raise_for_status(response)
        data = response.json()

        return RoamGroup(
            id=data.get("id", ""),
            name=data.get("name", ""),
            private=data.get("private", False),
            date_created=data.get("dateCreated", ""),
            raw=data,
        )

    async def list_group_members(self, group_id: str, *, limit: int = 100) -> list[str]:
        """List member IDs in a group via /group.members."""
        params = {"group": group_id, "limit": min(limit, 100)}
        response = await self._client.get("/group.members", params=params)
        _raise_for_status(response)
        data = response.json()
        return data.get("members", [])

    async def add_group_members(
        self, group_id: str, *, members: list[str] | None = None, admins: list[str] | None = None
    ) -> None:
        """Add members/admins to a group via /group.add."""
        payload: dict = {"group": group_id}
        if members:
            payload["members"] = members
        if admins:
            payload["admins"] = admins
        response = await self._client.post("/group.add", json=payload)
        _raise_for_status(response)

    # -- Users --

    async def list_users(self, *, limit: int = 100) -> list[RoamUser]:
        """List all users via /user.list."""
        params = {"limit": min(limit, 100)}
        response = await self._client.get("/user.list", params=params)
        _raise_for_status(response)
        data = response.json()

        return [
            RoamUser(
                id=user.get("id", ""),
                name=user.get("name", ""),
                email=user.get("email", ""),
                image_url=user.get("imageUrl", ""),
                is_admin=user.get("isAdmin", False),
                raw=user,
            )
            for user in data.get("users", [])
        ]

    async def lookup_user(self, email: str) -> RoamUser | None:
        """Look up a user by email via /user.lookup. Returns None if not found."""
        try:
            response = await self._client.get("/user.lookup", params={"email": email})
            _raise_for_status(response)
            data = response.json()
            return RoamUser(
                id=data.get("id", ""),
                name=data.get("name", ""),
                email=data.get("email", ""),
                image_url=data.get("imageUrl", ""),
                is_admin=data.get("isAdmin", False),
                raw=data,
            )
        except RoamNotFoundError:
            return None

    # -- Token --

    async def token_info(self) -> RoamTokenInfo:
        """Get current token info via /token.info."""
        response = await self._client.get("/token.info")
        _raise_for_status(response)
        data = response.json()
        roam = data.get("roam", {})

        return RoamTokenInfo(
            addr=data.get("addr", ""),
            scopes=data.get("scopes", []),
            roam_id=roam.get("id", ""),
            roam_name=roam.get("name", ""),
            raw=data,
        )
