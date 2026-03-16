"""Tests for Roam webhook ingestion (Task 6)."""

import uuid
from unittest.mock import patch

import pytest

from apps.audit.models import EventLog
from apps.conversations.factories import ConversationFactory
from apps.conversations.models import ConversationStatus
from apps.integrations_roam.webhook_service import WebhookService, _extract_fields, _is_bot_echo
from apps.messaging.models import ActorType, Message, MessageDirection, MessageSource
from apps.queues.factories import AnalystProfileFactory, QueueFactory


def _make_payload(
    *,
    sender_id="U-analyst-1",
    text="Looking into this now.",
    thread_key=None,
    chat_id="G-test-group",
    message_id=None,
    timestamp=1710600000,
):
    """Build a Roam-style webhook payload."""
    return {
        "senderId": sender_id,
        "text": text,
        "threadKey": thread_key or str(uuid.uuid4()),
        "chat": chat_id,
        "id": message_id or f"msg-{uuid.uuid4().hex[:8]}",
        "timestamp": timestamp,
    }


# --- Field Extraction Tests ---


class TestExtractFields:
    def test_extracts_standard_fields(self):
        payload = _make_payload(sender_id="U-123", text="hello", thread_key="tk-1")
        fields = _extract_fields(payload)
        assert fields.sender_id == "U-123"
        assert fields.text == "hello"
        assert fields.thread_key == "tk-1"

    def test_extracts_alternative_field_names(self):
        payload = {"sender_id": "U-456", "message": "hi", "thread_key": "tk-2", "chatId": "G-x"}
        fields = _extract_fields(payload)
        assert fields.sender_id == "U-456"
        assert fields.text == "hi"
        assert fields.thread_key == "tk-2"
        assert fields.chat_id == "G-x"

    def test_missing_fields_return_none(self):
        fields = _extract_fields({})
        assert fields.sender_id is None
        assert fields.text is None
        assert fields.thread_key is None


class TestIsBotEcho:
    def test_bot_prefix_detected(self):
        assert _is_bot_echo("B-some-bot-id") is True

    def test_user_prefix_not_bot(self):
        assert _is_bot_echo("U-some-user") is False

    def test_empty_not_bot(self):
        assert _is_bot_echo("") is False

    @patch("apps.integrations_roam.webhook_service.settings")
    def test_configured_bot_user_id(self, mock_settings):
        mock_settings.ROAM_BOT_USER_ID = "U-our-bot"
        assert _is_bot_echo("U-our-bot") is True


# --- Webhook Service Tests ---


@pytest.mark.django_db
class TestWebhookServiceChatMessage:
    def setup_method(self):
        self.service = WebhookService()

    def test_happy_path_creates_analyst_message(self):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(queue=queue, status=ConversationStatus.WAITING_SOC)
        payload = _make_payload(thread_key=str(conversation.roam_thread_key))

        with patch.object(self.service._publisher, "publish"):
            message = self.service.handle_chat_message(payload)

        assert message is not None
        assert message.actor_type == ActorType.ANALYST
        assert message.direction == MessageDirection.OUTBOUND
        assert message.source == MessageSource.ROAM_WEBHOOK
        assert message.body_plain == "Looking into this now."
        assert message.conversation_id == conversation.id

    def test_sets_first_response_at(self):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(
            queue=queue,
            status=ConversationStatus.QUEUED,
            first_response_at=None,
        )
        payload = _make_payload(thread_key=str(conversation.roam_thread_key))

        with patch.object(self.service._publisher, "publish"):
            self.service.handle_chat_message(payload)

        conversation.refresh_from_db()
        assert conversation.first_response_at is not None

    def test_does_not_overwrite_first_response_at(self):
        from django.utils import timezone

        queue = QueueFactory(key="soc-triage")
        first_time = timezone.now()
        conversation = ConversationFactory(
            queue=queue,
            status=ConversationStatus.WAITING_SOC,
            first_response_at=first_time,
        )
        payload = _make_payload(thread_key=str(conversation.roam_thread_key))

        with patch.object(self.service._publisher, "publish"):
            self.service.handle_chat_message(payload)

        conversation.refresh_from_db()
        assert conversation.first_response_at == first_time

    def test_transitions_queued_to_waiting_customer(self):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(queue=queue, status=ConversationStatus.QUEUED)
        payload = _make_payload(thread_key=str(conversation.roam_thread_key))

        with patch.object(self.service._publisher, "publish"):
            self.service.handle_chat_message(payload)

        conversation.refresh_from_db()
        assert conversation.status == ConversationStatus.WAITING_CUSTOMER

    def test_transitions_waiting_soc_to_waiting_customer(self):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(queue=queue, status=ConversationStatus.WAITING_SOC)
        payload = _make_payload(thread_key=str(conversation.roam_thread_key))

        with patch.object(self.service._publisher, "publish"):
            self.service.handle_chat_message(payload)

        conversation.refresh_from_db()
        assert conversation.status == ConversationStatus.WAITING_CUSTOMER

    def test_duplicate_webhook_is_idempotent(self):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(queue=queue, status=ConversationStatus.WAITING_SOC)
        payload = _make_payload(
            thread_key=str(conversation.roam_thread_key),
            message_id="roam-msg-fixed-id",
        )

        with patch.object(self.service._publisher, "publish"):
            msg1 = self.service.handle_chat_message(payload)
            msg2 = self.service.handle_chat_message(payload)

        assert msg1 is not None
        assert msg2 is None  # Duplicate ignored
        assert Message.objects.filter(conversation=conversation, actor_type=ActorType.ANALYST).count() == 1

    def test_bot_echo_is_ignored(self):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(queue=queue)
        payload = _make_payload(
            sender_id="B-our-bot",
            thread_key=str(conversation.roam_thread_key),
        )

        with patch.object(self.service._publisher, "publish"):
            result = self.service.handle_chat_message(payload)

        assert result is None
        assert Message.objects.filter(conversation=conversation, actor_type=ActorType.ANALYST).count() == 0

    def test_unknown_thread_key_is_logged(self):
        payload = _make_payload(thread_key="nonexistent-thread-key")

        with patch.object(self.service._publisher, "publish"):
            result = self.service.handle_chat_message(payload)

        assert result is None
        assert EventLog.objects.filter(event_type="roam_webhook.chat_message.orphaned").exists()

    def test_missing_text_skips_processing(self):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(queue=queue)
        payload = {
            "senderId": "U-analyst-1",
            "threadKey": str(conversation.roam_thread_key),
            "chat": "G-test",
        }
        # No "text" field

        with patch.object(self.service._publisher, "publish"):
            result = self.service.handle_chat_message(payload)

        assert result is None

    def test_missing_thread_key_skips_processing(self):
        payload = {"senderId": "U-analyst-1", "text": "Hello"}
        # No "threadKey" field

        with patch.object(self.service._publisher, "publish"):
            result = self.service.handle_chat_message(payload)

        assert result is None

    def test_empty_payload_returns_none(self):
        with patch.object(self.service._publisher, "publish"):
            result = self.service.handle_chat_message({})

        assert result is None

    def test_raw_payload_always_persisted(self):
        payload = _make_payload()

        with patch.object(self.service._publisher, "publish"):
            self.service.handle_chat_message(payload)

        assert EventLog.objects.filter(event_type="roam_webhook.chat_message.raw").exists()

    def test_analyst_profile_used_when_available(self):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(queue=queue, status=ConversationStatus.WAITING_SOC)
        analyst = AnalystProfileFactory(
            external_user_id="U-analyst-1",
            display_name="Alice Analyst",
        )
        payload = _make_payload(
            sender_id="U-analyst-1",
            thread_key=str(conversation.roam_thread_key),
        )

        with patch.object(self.service._publisher, "publish"):
            message = self.service.handle_chat_message(payload)

        assert message.actor_id == analyst.external_user_id

    def test_publishes_sse_event(self):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(queue=queue, status=ConversationStatus.WAITING_SOC)
        payload = _make_payload(thread_key=str(conversation.roam_thread_key))

        with patch.object(self.service._publisher, "publish") as mock_publish:
            self.service.handle_chat_message(payload)

        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args
        assert call_kwargs[1]["event_type"] == "message.created"
        assert call_kwargs[1]["conversation_id"] == str(conversation.id)


@pytest.mark.django_db
class TestWebhookServiceReaction:
    def test_reaction_stores_event_log(self):
        service = WebhookService()
        payload = {"type": "reaction", "emoji": "thumbsup", "messageId": "msg-123"}

        with patch.object(service._publisher, "publish"):
            service.handle_reaction(payload)

        assert EventLog.objects.filter(event_type="roam_webhook.reaction.raw").exists()


# --- Webhook API View Tests ---


@pytest.mark.django_db
class TestChatMessageWebhookAPI:
    def test_webhook_returns_200_on_success(self, api_client):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(queue=queue)
        payload = _make_payload(thread_key=str(conversation.roam_thread_key))

        response = api_client.post(
            "/webhooks/roam/chat-message",
            data=payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["status"] == "ok"

    def test_webhook_returns_200_on_ignored_payload(self, api_client):
        response = api_client.post(
            "/webhooks/roam/chat-message",
            data={},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["status"] == "ignored"

    def test_webhook_returns_200_on_bot_echo(self, api_client):
        queue = QueueFactory(key="soc-triage")
        conversation = ConversationFactory(queue=queue)
        payload = _make_payload(
            sender_id="B-bot-id",
            thread_key=str(conversation.roam_thread_key),
        )

        response = api_client.post(
            "/webhooks/roam/chat-message",
            data=payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["status"] == "ignored"


@pytest.mark.django_db
class TestReactionWebhookAPI:
    def test_reaction_webhook_returns_200(self, api_client):
        response = api_client.post(
            "/webhooks/roam/reaction",
            data={"type": "reaction", "emoji": "thumbsup"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["status"] == "ok"
