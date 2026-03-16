"""Mock Roam client for testing — records all calls and returns canned responses."""

import logging
from dataclasses import dataclass, field

from .types import (
    RoamChat,
    RoamGroup,
    RoamMessage,
    RoamPostResponse,
    RoamTokenInfo,
    RoamUser,
)

logger = logging.getLogger(__name__)


@dataclass
class MockCall:
    method: str
    args: tuple
    kwargs: dict


class MockRoamClient:
    """In-memory mock that implements the same interface as RoamClient.

    Stores all calls for assertion in tests and returns predictable responses.
    """

    def __init__(self):
        self.calls: list[MockCall] = []
        self._post_counter = 0

    def _record(self, method: str, *args, **kwargs):
        self.calls.append(MockCall(method=method, args=args, kwargs=kwargs))
        logger.debug("MockRoamClient.%s called with args=%s kwargs=%s", method, args, kwargs)

    def get_calls(self, method: str) -> list[MockCall]:
        return [c for c in self.calls if c.method == method]

    async def post_message(
        self, chat_id: str, text: str, *, thread_key: str | None = None, markdown: bool = True
    ) -> RoamPostResponse:
        self._record("post_message", chat_id, text, thread_key=thread_key, markdown=markdown)
        self._post_counter += 1
        return RoamPostResponse(
            chat=chat_id,
            thread_timestamp=self._post_counter * 1000,
            timestamp=self._post_counter * 1000,
            raw={"chat": chat_id, "threadTimestamp": self._post_counter * 1000},
        )

    async def get_chat_history(
        self, chat_id: str, *, thread_timestamp: int | None = None, limit: int = 50
    ) -> list[RoamMessage]:
        self._record("get_chat_history", chat_id, thread_timestamp=thread_timestamp, limit=limit)
        return []

    async def list_chats(self, *, limit: int = 100) -> list[RoamChat]:
        self._record("list_chats", limit=limit)
        return []

    async def send_typing(self, chat_id: str, *, thread_timestamp: int | None = None) -> None:
        self._record("send_typing", chat_id, thread_timestamp=thread_timestamp)

    async def create_group(self, name: str, *, private: bool = True) -> RoamGroup:
        self._record("create_group", name, private=private)
        return RoamGroup(id=f"G-mock-{name}", name=name, private=private, raw={})

    async def list_group_members(self, group_id: str, *, limit: int = 100) -> list[str]:
        self._record("list_group_members", group_id, limit=limit)
        return []

    async def add_group_members(
        self, group_id: str, *, members: list[str] | None = None, admins: list[str] | None = None
    ) -> None:
        self._record("add_group_members", group_id, members=members, admins=admins)

    async def list_users(self, *, limit: int = 100) -> list[RoamUser]:
        self._record("list_users", limit=limit)
        return []

    async def lookup_user(self, email: str) -> RoamUser | None:
        self._record("lookup_user", email)
        return None

    async def token_info(self) -> RoamTokenInfo:
        self._record("token_info")
        return RoamTokenInfo(addr="B-mock-bot", scopes=["chat:post", "chat:history"], raw={})
