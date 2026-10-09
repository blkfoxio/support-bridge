"""Tests for the customer delivery dispatcher."""

from unittest.mock import MagicMock, patch

import pytest

from apps.conversations.factories import ConversationFactory
from apps.messaging import delivery
from apps.messaging.delivery import CustomerDeliveryDispatcher, register_channel_deliverer
from apps.messaging.factories import MessageFactory
from apps.queues.factories import QueueFactory


class FakeDeliverer:
    def __init__(self, name="fake", applies=True, fail=False):
        self.name = name
        self.applies = applies
        self.fail = fail
        self.delivered = []

    def applies_to(self, conversation):
        return self.applies

    def deliver_message(self, conversation, message, sender_name):
        if self.fail:
            raise RuntimeError("boom")
        self.delivered.append((conversation.id, message.id, sender_name))


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch):
    monkeypatch.setattr(delivery, "_channel_deliverers", [])


@pytest.fixture
def conversation(db):
    return ConversationFactory(queue=QueueFactory(key="soc-triage"))


@pytest.fixture
def dispatcher():
    return CustomerDeliveryDispatcher(publisher=MagicMock())


@pytest.mark.django_db
class TestCustomerDeliveryDispatcher:
    def test_publishes_sse_and_sends_push(self, conversation, dispatcher):
        message = MessageFactory(conversation=conversation, body_plain="On it")

        with patch.object(delivery, "send_push_notification") as push:
            dispatcher.deliver_message(conversation, message, "Jane")

        assert dispatcher._publisher.publish.call_args.kwargs["event_type"] == "message.created"
        push.assert_called_once()
        assert push.call_args.kwargs["customer_cognito_sub"] == conversation.customer_user_id
        assert push.call_args.kwargs["sender_name"] == "Jane"

    def test_applicable_channel_receives_message(self, conversation, dispatcher):
        message = MessageFactory(conversation=conversation)
        slack, teams = FakeDeliverer("slack"), FakeDeliverer("teams", applies=False)
        register_channel_deliverer(slack)
        register_channel_deliverer(teams)

        with patch.object(delivery, "send_push_notification"):
            dispatcher.deliver_message(conversation, message, "Jane")

        assert slack.delivered == [(conversation.id, message.id, "Jane")]
        assert teams.delivered == []

    def test_failures_are_isolated(self, conversation, dispatcher):
        message = MessageFactory(conversation=conversation)
        dispatcher._publisher.publish.side_effect = RuntimeError("redis down")
        broken, healthy = FakeDeliverer("broken", fail=True), FakeDeliverer("healthy")
        register_channel_deliverer(broken)
        register_channel_deliverer(healthy)

        with patch.object(delivery, "send_push_notification", side_effect=RuntimeError("push down")):
            dispatcher.deliver_message(conversation, message, "Jane")

        assert len(healthy.delivered) == 1

    def test_register_is_idempotent_by_name(self):
        register_channel_deliverer(FakeDeliverer("slack"))
        register_channel_deliverer(FakeDeliverer("slack"))

        assert len(delivery._channel_deliverers) == 1
