"""Model tests — run with SQLite for speed (no Postgres needed)."""

import pytest

from apps.conversations.models import ConversationStatus, SourceChannel
from apps.messaging.models import ActorType, MessageDirection, MessageSource, MessageType


class TestEnumChoices:
    """Verify all TextChoices enums have the expected values."""

    def test_conversation_status_values(self):
        expected = {"new", "queued", "assigned", "waiting_customer", "waiting_soc", "resolved", "closed"}
        assert set(ConversationStatus.values) == expected

    def test_source_channel_values(self):
        expected = {"mobile_ios", "mobile_android", "web"}
        assert set(SourceChannel.values) == expected

    def test_actor_type_values(self):
        expected = {"customer", "analyst", "system"}
        assert set(ActorType.values) == expected

    def test_message_direction_values(self):
        expected = {"inbound", "outbound"}
        assert set(MessageDirection.values) == expected

    def test_message_source_values(self):
        expected = {"customer_api", "roam_webhook", "internal"}
        assert set(MessageSource.values) == expected

    def test_message_type_values(self):
        expected = {"text", "system_note", "status"}
        assert set(MessageType.values) == expected
