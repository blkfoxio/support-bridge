"""Shared helpers for Slack integration tests: a fake Slack client and event builders."""

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


_counter = [0]


def make_event(event, event_id=None):
    _counter[0] += 1
    return {"type": "event_callback", "team_id": TEAM, "event_id": event_id or f"Ev{_counter[0]}", "event": event}


def make_msg(text, *, user="U1", ts="100.1", channel="C1", thread_ts=None, channel_type="channel", **extra):
    ev = {"type": "message", "user": user, "text": text, "ts": ts, "channel": channel, "channel_type": channel_type}
    if thread_ts:
        ev["thread_ts"] = thread_ts
    ev.update(extra)
    return make_event(ev)


def only_conversation():
    from apps.conversations.models import Conversation

    return Conversation.objects.get()
