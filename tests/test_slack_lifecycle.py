"""Tests for conversation lifecycle in Slack (phase 5): status notices and Close/Reopen buttons."""

import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlencode

import pytest
from django.test import Client
from django.utils import timezone

from apps.conversations.factories import ConversationFactory
from apps.conversations.models import Conversation, ConversationStatus
from apps.conversations.services import ConversationService
from apps.conversations.tasks import _check_customer_idle, _check_resolved_idle
from apps.integrations_roam.mock_client import MockRoamClient
from apps.integrations_slack.inbound import handle_event
from apps.integrations_slack.interactivity import handle_interaction
from apps.integrations_slack.outbound import ACTION_CLOSE, ACTION_REOPEN, STATUS_CLOSED_TEXT, STATUS_REOPENED_TEXT
from apps.queues.models import Queue
from tests.slack_helpers import TEAM, make_msg

SIGNING_SECRET = "lifecycle-secret"


def _start(slack):
    handle_event(make_msg("Is our firewall down?"))
    slack.posts.clear()
    return Conversation.objects.get()


def _resolve(conv):
    Conversation.objects.filter(id=conv.id, status=ConversationStatus.QUEUED).update(
        status=ConversationStatus.WAITING_CUSTOMER  # an analyst has replied
    )
    with patch("apps.conversations.services.post_status_to_roam"):
        ConversationService(MockRoamClient()).resolve_conversation(conversation_id=conv.id, actor_id="analyst")
    conv.refresh_from_db()


def _click(action_id, conv, *, team=TEAM, user="U2"):
    return {
        "type": "block_actions",
        "team": {"id": team},
        "user": {"id": user},
        "response_url": "https://hooks.slack.test/resp",
        "actions": [{"action_id": action_id, "value": str(conv.id)}],
    }


@pytest.mark.django_db
class TestStatusNotices:
    def test_resolve_posts_buttons_in_thread(self, install, slack):
        conv = _start(slack)
        _resolve(conv)

        post = slack.posts[-1]
        assert post["thread_ts"] == "100.1"
        assert post["text"].startswith("✅ Your analyst has resolved this conversation")
        buttons = post["blocks"][1]["elements"]
        assert [b["action_id"] for b in buttons] == [ACTION_CLOSE, ACTION_REOPEN]
        assert {b["value"] for b in buttons} == {str(conv.id)}

    def test_close_and_reopen_from_app_post_notices(self, install, slack):
        conv = _start(slack)
        _resolve(conv)
        service = ConversationService(MockRoamClient())
        with patch("apps.conversations.services.post_status_to_roam"):
            service.reopen_conversation(conversation_id=conv.id, user_id=conv.customer_user_id)
            assert slack.posts[-1]["text"] == STATUS_REOPENED_TEXT
            service.close_conversation(conversation_id=conv.id, user_id=conv.customer_user_id)
        assert slack.posts[-1]["text"] == STATUS_CLOSED_TEXT

    def test_auto_resolve_and_auto_close_post_notices(self, install, slack):
        conv = _start(slack)
        long_ago = timezone.now() - timedelta(days=4)
        Conversation.objects.filter(id=conv.id).update(status=ConversationStatus.WAITING_CUSTOMER,
                                                        last_message_at=long_ago)
        with patch("apps.conversations.tasks.post_status_to_roam"):
            _check_customer_idle(timezone.now())
            assert "blocks" in slack.posts[-1]  # auto-resolve offers the buttons
            Conversation.objects.filter(id=conv.id).update(resolved_at=long_ago)
            _check_resolved_idle(timezone.now())
        assert slack.posts[-1]["text"] == STATUS_CLOSED_TEXT

    def test_non_slack_conversation_unaffected(self, install, slack):
        conv = ConversationFactory(queue=Queue.objects.first(), status=ConversationStatus.WAITING_SOC)
        _resolve(conv)
        assert slack.posts == []


@pytest.mark.django_db
class TestButtons:
    def test_close_button(self, install, slack):
        conv = _start(slack)
        _resolve(conv)
        with patch("apps.integrations_slack.interactivity.httpx.post") as respond, \
                patch("apps.conversations.services.post_status_to_roam"):
            handle_interaction(_click(ACTION_CLOSE, conv))

        conv.refresh_from_db()
        assert conv.status == ConversationStatus.CLOSED
        assert "<@U2> closed this conversation" in respond.call_args.kwargs["json"]["text"]
        assert respond.call_args.kwargs["json"]["replace_original"] is True
        assert conv.participants.filter(user_id=f"slack:{TEAM}:U2").exists()

    def test_reopen_button(self, install, slack):
        conv = _start(slack)
        _resolve(conv)
        with patch("apps.integrations_slack.interactivity.httpx.post") as respond, \
                patch("apps.conversations.services.post_status_to_roam") as roam:
            handle_interaction(_click(ACTION_REOPEN, conv))

        conv.refresh_from_db()
        assert conv.status == ConversationStatus.WAITING_SOC
        assert "still need help" in respond.call_args.kwargs["json"]["text"]
        roam.assert_called_once()

    def test_stale_button_reports_current_status(self, install, slack):
        conv = _start(slack)
        _resolve(conv)
        Conversation.objects.filter(id=conv.id).update(status=ConversationStatus.CLOSED)
        with patch("apps.integrations_slack.interactivity.httpx.post") as respond:
            handle_interaction(_click(ACTION_REOPEN, conv))

        assert "already closed" in respond.call_args.kwargs["json"]["text"]
        assert Conversation.objects.get().status == ConversationStatus.CLOSED

    def test_button_from_other_workspace_ignored(self, install, slack):
        conv = _start(slack)
        _resolve(conv)
        with patch("apps.integrations_slack.interactivity.httpx.post") as respond:
            handle_interaction(_click(ACTION_CLOSE, conv, team="T-evil"))

        respond.assert_not_called()
        assert Conversation.objects.get().status == ConversationStatus.RESOLVED


@pytest.mark.django_db
class TestInteractivityEndpoint:
    def _post(self, payload, secret):
        body = urlencode({"payload": json.dumps(payload)}).encode()
        ts = str(int(time.time()))
        sig = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
        return Client().post("/slack/interactivity", data=body, content_type="application/x-www-form-urlencoded",
                             HTTP_X_SLACK_REQUEST_TIMESTAMP=ts, HTTP_X_SLACK_SIGNATURE=sig)

    def test_signed_click_is_processed(self, install, slack, settings):
        settings.SLACK_SIGNING_SECRET = SIGNING_SECRET
        conv = _start(slack)
        _resolve(conv)
        with patch("apps.integrations_slack.interactivity.httpx.post"), \
                patch("apps.conversations.services.post_status_to_roam"):
            response = self._post(_click(ACTION_CLOSE, conv), SIGNING_SECRET)

        assert response.status_code == 200
        assert Conversation.objects.get().status == ConversationStatus.CLOSED

    def test_bad_signature_rejected(self, install, slack, settings):
        settings.SLACK_SIGNING_SECRET = SIGNING_SECRET
        assert self._post({"type": "block_actions"}, "wrong").status_code == 401
