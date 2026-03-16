"""Typed response models for Roam API v0 responses.

Roam uses tagged UUIDs with prefixes: U- (user), C- (chat), G- (group), D- (DM), B- (bot).
"""

from dataclasses import dataclass, field


@dataclass
class RoamMessage:
    """A message from chat.post or chat.history."""
    id: str = ""
    text: str = ""
    sender_id: str = ""
    sender_name: str = ""
    thread_key: str | None = None
    thread_timestamp: int | None = None
    timestamp: int | None = None
    created_at: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class RoamPostResponse:
    """Response from chat.post."""
    chat: str = ""  # Tagged UUID (C-...)
    thread_timestamp: int | None = None
    timestamp: int | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class RoamChat:
    """A chat from chat.list."""
    id: str = ""  # Tagged UUID
    name: str = ""
    group: str | None = None  # Tagged UUID (G-...) for channels
    started: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class RoamGroup:
    """A group from group.create."""
    id: str = ""  # Tagged UUID (G-...)
    name: str = ""
    private: bool = False
    date_created: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class RoamUser:
    """A user from user.list or user.lookup."""
    id: str = ""  # Tagged UUID (U-...)
    name: str = ""
    email: str = ""
    image_url: str = ""
    is_admin: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class RoamTokenInfo:
    """Response from token.info."""
    addr: str = ""  # Tagged UUID
    scopes: list[str] = field(default_factory=list)
    roam_id: str = ""
    roam_name: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class RoamWebhookSubscription:
    """Placeholder for webhook subscription tracking."""
    id: str = ""
    url: str = ""
    events: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
