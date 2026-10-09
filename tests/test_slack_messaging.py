"""Tests for Slack <-> conversation messaging (phase 4)."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.core.cache import cache
from django.utils import timezone

from apps.conversations.models import Conversation, ConversationStatus
from apps.conversations.services import ConversationService
from apps.identities.models import ExternalIdentity
from apps.integrations_roam.mock_client import MockRoamClient
from apps.integrations_slack.inbound import ACK_NEW, ACK_REOPENED, NOTICE_PENDING, NOTICE_UNLINKED, handle_event
from apps.integrations_slack.models import SlackChannel, SlackThread
from apps.integrations_slack.services import record_installation
from apps.messaging.delivery import CustomerDeliveryDispatcher
from apps.messaging.models import ActorType, Message, MessageDirection, MessageSource
from apps.organizations.models import Organization
from apps.queues.factories import QueueFactory

TEAM = "T1"
BOT = "UBOT"


class FakeSlack:
    """Stands in for SlackClient; records posts and serves canned users/channels/messages."""

    def __init__(self):
        self.posts = []
        self.joined = []
        self.users = {
            "U1": {"id": "U1", "profile": {"display_name": "Jane", "email": "jane@acme.com"}},
            "U2": {"id": "U2", "profile": {"real_name": "Bob", "email": "bob@acme.com"}},
            "UB": {"id": "UB", "is_bot": True, "profile": {}},
        }
        self.messages = {}
        self._ts = 9000

    def __call__(self, token=""):
        return self

    def post_message(self, channel, text, *, thread_ts=None, **extra):
        self._ts += 1
        self.posts.append({"channel": channel, "text": text, "thread_ts": thread_ts, **extra})
        return {"ok": True, "ts": f"{self._ts}.000"}

    def user_info(self, user_id):
        return self.users[user_id]

    def conversation_info(self, channel):
        return {"id": channel, "name": "cyflare-help", "is_private": False}

    def get_message(self, channel, ts):
        return self.messages.get((channel, ts))

    def join_channel(self, channel):
        self.joined.append(channel)
        return {"ok": True}


@pytest.fixture
def slack(settings):
    settings.SLACK_TOKEN_ENCRYPTION_KEY = Fernet.generate_key().decode()
    settings.ROAM_API_TOKEN = ""
    cache.clear()
    fake = FakeSlack()
    with patch("apps.integrations_slack.inbound.SlackClient", fake), \
            patch("apps.integrations_slack.outbound.SlackClient", fake), \
            patch("apps.integrations_slack.services.SlackClient", fake):
        yield fake


@pytest.fixture
def install(db, slack):
    QueueFactory(key="soc-triage")
    inst, _ = record_installation(
        {"access_token": "xoxb-t", "bot_user_id": BOT, "team": {"id": TEAM, "name": "Acme"}},
        org_id="42", user_id="admin",
    )
    return inst


_counter = [0]


def _event(event, event_id=None):
    _counter[0] += 1
    return {"type": "event_callback", "team_id": TEAM, "event_id": event_id or f"Ev{_counter[0]}", "event": event}


def _msg(text, *, user="U1", ts="100.1", channel="C1", thread_ts=None, channel_type="channel", **extra):
    ev = {"type": "message", "user": user, "text": text, "ts": ts, "channel": channel, "channel_type": channel_type}
    if thread_ts:
        ev["thread_ts"] = thread_ts
    ev.update(extra)
    return _event(ev)


def _only_conversation():
    return Conversation.objects.get()


@pytest.mark.django_db
class TestInboundChannelMessages:
    def test_top_level_message_starts_conversation(self, install, slack):
        handle_event(_msg("Is our firewall down?"))

        conv = _only_conversation()
        assert conv.source_channel == "slack"
        assert conv.customer_org_id == "42"
        assert conv.customer_user_id == f"slack:{TEAM}:U1"
        assert conv.customer_name == "Jane"
        msg = conv.messages.get()
        assert msg.source == MessageSource.SLACK
        assert msg.metadata["slack_ts"] == "100.1"
        assert SlackThread.objects.get().thread_ts == "100.1"
        assert slack.posts == [{"channel": "C1", "text": ACK_NEW, "thread_ts": "100.1"}]
        assert SlackChannel.objects.get().name == "cyflare-help"
        assert ExternalIdentity.objects.get().email == "jane@acme.com"
        assert conv.participants.get().identity is not None

    def test_thread_reply_from_another_person_joins_same_conversation(self, install, slack):
        handle_event(_msg("Is our firewall down?"))
        handle_event(_msg("Same here", user="U2", ts="100.2", thread_ts="100.1"))

        conv = _only_conversation()
        assert conv.messages.count() == 2
        assert set(conv.participants.values_list("user_id", flat=True)) == {f"slack:{TEAM}:U1", f"slack:{TEAM}:U2"}
        assert conv.messages.last().metadata["customer_name"] == "Bob"

    def test_reply_in_untracked_thread_ignored(self, install, slack):
        handle_event(_msg("random chat", ts="200.2", thread_ts="200.1"))
        assert not Conversation.objects.exists()

    def test_top_level_post_within_merge_window_joins_open_conversation(self, install, slack):
        handle_event(_msg("first", ts="100.1"))
        handle_event(_msg("also this", ts="100.5"))

        conv = _only_conversation()
        assert conv.messages.count() == 2
        assert set(SlackThread.objects.values_list("thread_ts", flat=True)) == {"100.1", "100.5"}
        # a reply to the merged post lands in the same conversation
        handle_event(_msg("more", ts="100.6", thread_ts="100.5"))
        assert conv.messages.count() == 3

    def test_top_level_post_outside_merge_window_starts_new_conversation(self, install, slack):
        handle_event(_msg("first", ts="100.1"))
        Conversation.objects.update(last_message_at=timezone.now() - timedelta(hours=2))
        handle_event(_msg("new problem", ts="300.1"))

        assert Conversation.objects.count() == 2

    def test_reply_to_closed_conversation_starts_linked_one(self, install, slack):
        handle_event(_msg("first", ts="100.1"))
        old = _only_conversation()
        Conversation.objects.update(status=ConversationStatus.CLOSED)

        handle_event(_msg("it's back", ts="100.9", thread_ts="100.1"))

        new = Conversation.objects.exclude(id=old.id).get()
        assert new.messages.get().metadata["previous_conversation_id"] == str(old.id)
        assert slack.posts[-1] == {"channel": "C1", "text": ACK_REOPENED, "thread_ts": "100.1"}
        handle_event(_msg("still broken", ts="101.0", thread_ts="100.1"))
        assert new.messages.count() == 2

    def test_reply_reopens_resolved_conversation(self, install, slack):
        handle_event(_msg("first", ts="100.1"))
        Conversation.objects.update(status=ConversationStatus.RESOLVED)
        handle_event(_msg("not fixed", ts="100.2", thread_ts="100.1"))

        assert _only_conversation().status == ConversationStatus.WAITING_SOC

    def test_duplicate_event_processed_once(self, install, slack):
        payload = _msg("hello")
        handle_event(payload)
        handle_event(payload)
        assert Message.objects.count() == 1

    @pytest.mark.parametrize("extra", [
        {"bot_id": "B123"},
        {"subtype": "message_changed"},
        {"subtype": "channel_join"},
        {"user": BOT},
        {"user_team": "T-other"},
        {"channel_type": "mpim"},
    ])
    def test_ignored_messages(self, install, slack, extra):
        handle_event(_msg("hi", **extra))
        assert not Conversation.objects.exists()

    def test_bot_user_ignored(self, install, slack):
        handle_event(_msg("beep", user="UB"))
        assert not Conversation.objects.exists()

    def test_file_share_noted(self, install, slack):
        handle_event(_msg("see screenshot", subtype="file_share", files=[{"id": "F1"}]))
        assert "📎 1 file(s) attached" in _only_conversation().messages.get().body_plain

    def test_disabled_channel_ignored(self, install, slack):
        SlackChannel.objects.create(installation=install, channel_id="C1", enabled=False)
        handle_event(_msg("hi"))
        assert not Conversation.objects.exists()


@pytest.mark.django_db
class TestInboundDirectMessages:
    def test_dm_is_one_rolling_conversation(self, install, slack):
        handle_event(_msg("help", channel="D1", channel_type="im", ts="1.1"))
        handle_event(_msg("more detail", channel="D1", channel_type="im", ts="1.2"))

        conv = _only_conversation()
        assert conv.messages.count() == 2
        assert SlackThread.objects.get().thread_ts == ""
        assert slack.posts[0]["thread_ts"] is None

    def test_dm_after_close_starts_new_conversation(self, install, slack):
        handle_event(_msg("help", channel="D1", channel_type="im", ts="1.1"))
        Conversation.objects.update(status=ConversationStatus.CLOSED)
        handle_event(_msg("again", channel="D1", channel_type="im", ts="2.1"))

        assert Conversation.objects.count() == 2


@pytest.mark.django_db
class TestOrgSettings:
    def test_unlinked_users_blocked_when_disallowed(self, install, slack):
        Organization.objects.filter(org_id="42").update(slack_allow_unlinked_users=False)
        handle_event(_msg("hi"))
        handle_event(_msg("hello?", ts="100.2"))

        assert not Conversation.objects.exists()
        assert [p["text"] for p in slack.posts] == [NOTICE_UNLINKED]  # notified once

    def test_linked_user_allowed_when_unlinked_disallowed(self, install, slack):
        Organization.objects.filter(org_id="42").update(slack_allow_unlinked_users=False)
        ExternalIdentity.objects.create(provider="slack", team_id=TEAM, external_user_id="U1", org_id="42",
                                        linked_user_id="one-user")
        handle_event(_msg("hi"))

        assert _only_conversation().customer_user_id == "one-user"

    def test_emoji_mode_ignores_plain_posts_and_starts_on_reaction(self, install, slack):
        Organization.objects.filter(org_id="42").update(slack_conversation_trigger="emoji")
        handle_event(_msg("just chatting", ts="5.1"))
        assert not Conversation.objects.exists()

        slack.messages[("C1", "5.1")] = {"type": "message", "user": "U2", "text": "just chatting", "ts": "5.1"}
        handle_event(_event({"type": "reaction_added", "user": "U1", "reaction": "speech_balloon",
                             "item": {"type": "message", "channel": "C1", "ts": "5.1"}}))

        conv = _only_conversation()
        assert conv.customer_name == "Bob"  # the message author, not the reactor
        handle_event(_msg("follow up", user="U1", ts="5.2", thread_ts="5.1"))
        assert conv.messages.count() == 2

    def test_channel_override_beats_org_default(self, install, slack):
        Organization.objects.filter(org_id="42").update(slack_conversation_trigger="emoji")
        SlackChannel.objects.create(installation=install, channel_id="C1", conversation_trigger="all_messages")
        handle_event(_msg("hi"))
        assert Conversation.objects.count() == 1

    def test_wrong_emoji_ignored(self, install, slack):
        Organization.objects.filter(org_id="42").update(slack_conversation_trigger="emoji")
        slack.messages[("C1", "5.1")] = {"type": "message", "user": "U2", "text": "x", "ts": "5.1"}
        handle_event(_event({"type": "reaction_added", "reaction": "thumbsup",
                             "item": {"type": "message", "channel": "C1", "ts": "5.1"}}))
        assert not Conversation.objects.exists()

    def test_auto_join_matching_public_channel(self, install, slack):
        Organization.objects.filter(org_id="42").update(slack_auto_join_pattern="cyflare-*")
        handle_event(_event({"type": "channel_created", "channel": {"id": "C9", "name": "cyflare-alerts"}}))
        handle_event(_event({"type": "channel_created", "channel": {"id": "C8", "name": "random"}}))

        assert slack.joined == ["C9"]
        assert SlackChannel.objects.get(channel_id="C9").name == "cyflare-alerts"

    def test_bot_joining_registers_channel(self, install, slack):
        handle_event(_event({"type": "member_joined_channel", "user": BOT, "channel": "C5"}))
        assert SlackChannel.objects.filter(channel_id="C5").exists()


@pytest.mark.django_db
class TestPendingInstall:
    def test_pending_workspace_gets_notice_not_conversation(self, db, slack):
        QueueFactory(key="soc-triage")
        record_installation({"access_token": "xoxb-t", "bot_user_id": BOT, "team": {"id": TEAM}},
                            org_id=None, user_id=None)
        handle_event(_msg("hi"))

        assert not Conversation.objects.exists()
        assert slack.posts[0]["text"] == NOTICE_PENDING


@pytest.mark.django_db
class TestOutbound:
    def _start(self, slack):
        handle_event(_msg("Is our firewall down?"))
        slack.posts.clear()
        return _only_conversation()

    def test_analyst_reply_posts_into_thread_with_name(self, install, slack):
        conv = self._start(slack)
        reply = Message.objects.create(conversation=conv, actor_type=ActorType.ANALYST, actor_id="U-a",
                                       direction=MessageDirection.OUTBOUND, source=MessageSource.ROAM_WEBHOOK,
                                       body_plain="Looking now")
        with patch("apps.messaging.delivery.send_push_notification"):
            CustomerDeliveryDispatcher(publisher=_NullPublisher()).deliver_message(conv, reply, "Matt")

        assert slack.posts == [{"channel": "C1", "text": "Looking now", "thread_ts": "100.1",
                                "username": "Matt · Cyflare SOC"}]
        reply.refresh_from_db()
        assert reply.metadata["slack_posted_ts"]

    def test_app_message_mirrored_to_slack(self, install, slack):
        conv = self._start(slack)
        ConversationService(MockRoamClient()).send_message(
            conversation_id=conv.id, user_id=conv.customer_user_id, body="Adding detail from the app",
            idempotency_key="app-1",
        )
        assert slack.posts[-1]["text"] == "*Jane* (via Cyflare app):\nAdding detail from the app"
        assert slack.posts[-1]["thread_ts"] == "100.1"

    def test_slack_messages_not_echoed(self, install, slack):
        self._start(slack)
        handle_event(_msg("reply in slack", user="U2", ts="100.2", thread_ts="100.1"))
        assert slack.posts == []

    def test_inactive_workspace_skips_delivery(self, install, slack):
        conv = self._start(slack)
        install.status = "inactive"
        install.save()
        reply = Message.objects.create(conversation=conv, actor_type=ActorType.ANALYST, actor_id="U-a",
                                       direction=MessageDirection.OUTBOUND, source=MessageSource.ROAM_WEBHOOK,
                                       body_plain="hi")
        with patch("apps.messaging.delivery.send_push_notification"):
            CustomerDeliveryDispatcher(publisher=_NullPublisher()).deliver_message(conv, reply, "Matt")
        assert slack.posts == []

    def test_dm_reply_posts_flat(self, install, slack):
        handle_event(_msg("help", channel="D1", channel_type="im", ts="1.1"))
        slack.posts.clear()
        conv = _only_conversation()
        reply = Message.objects.create(conversation=conv, actor_type=ActorType.ANALYST, actor_id="U-a",
                                       direction=MessageDirection.OUTBOUND, source=MessageSource.ROAM_WEBHOOK,
                                       body_plain="hi")
        with patch("apps.messaging.delivery.send_push_notification"):
            CustomerDeliveryDispatcher(publisher=_NullPublisher()).deliver_message(conv, reply, "Matt")
        assert slack.posts[0]["channel"] == "D1"
        assert slack.posts[0]["thread_ts"] is None


class _NullPublisher:
    def publish(self, **kwargs):
        return ""
