"""Protocol defining the Roam integration interface.

All Roam API interaction goes through this protocol, making it easy to
swap between real and mock implementations.
"""

from typing import Protocol

from .types import (
    RoamChat,
    RoamGroup,
    RoamMessage,
    RoamPostResponse,
    RoamTokenInfo,
    RoamUser,
)


class RoamAdapter(Protocol):
    """Interface for Roam API operations used by the support bridge."""

    async def post_message(
        self, chat_id: str, text: str, *, thread_key: str | None = None, markdown: bool = True
    ) -> RoamPostResponse:
        """Post a message to a chat/group. Use thread_key for threaded replies."""
        ...

    async def get_chat_history(
        self, chat_id: str, *, thread_timestamp: int | None = None, limit: int = 50
    ) -> list[RoamMessage]:
        """Get message history for a chat, optionally filtered to a thread."""
        ...

    async def list_chats(self, *, limit: int = 100) -> list[RoamChat]:
        """List accessible chats (DMs, MultiDMs, Channels)."""
        ...

    async def send_typing(self, chat_id: str, *, thread_timestamp: int | None = None) -> None:
        """Show typing indicator in a chat."""
        ...

    async def create_group(self, name: str, *, private: bool = True) -> RoamGroup:
        """Create a new group/channel."""
        ...

    async def list_group_members(self, group_id: str, *, limit: int = 100) -> list[str]:
        """List member IDs in a group."""
        ...

    async def add_group_members(self, group_id: str, *, members: list[str] | None = None, admins: list[str] | None = None) -> None:
        """Add members and/or admins to a group."""
        ...

    async def list_users(self, *, limit: int = 100) -> list[RoamUser]:
        """List all users in the organization."""
        ...

    async def lookup_user(self, email: str) -> RoamUser | None:
        """Look up a user by email. Returns None if not found."""
        ...

    async def token_info(self) -> RoamTokenInfo:
        """Get info about the current access token."""
        ...
