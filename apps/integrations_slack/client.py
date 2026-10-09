"""Minimal Slack Web API client (httpx), mirroring the Roam client's retry behaviour."""

import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

SLACK_API_BASE_URL = "https://slack.com/api"


class SlackApiError(Exception):
    def __init__(self, method: str, error: str):
        super().__init__(f"Slack {method} failed: {error}")
        self.method = method
        self.error = error


class SlackRateLimitError(SlackApiError):
    pass


class SlackClient:
    def __init__(self, token: str = "", timeout: float = 10.0):
        self._token = token
        self._timeout = timeout

    @retry(
        retry=retry_if_exception_type(SlackRateLimitError),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def call(self, method: str, *, json: dict | None = None, data: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(f"{SLACK_API_BASE_URL}/{method}", json=json, data=data, headers=headers)
        if resp.status_code == 429:
            raise SlackRateLimitError(method, "ratelimited")
        resp.raise_for_status()
        body = resp.json()
        if not body.get("ok"):
            raise SlackApiError(method, body.get("error", "unknown_error"))
        return body

    def post_message(self, channel: str, text: str, *, thread_ts: str | None = None, **extra) -> dict:
        payload = {"channel": channel, "text": text, **extra}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return self.call("chat.postMessage", json=payload)

    # Read methods take form-encoded bodies.
    def user_info(self, user_id: str) -> dict:
        return self.call("users.info", data={"user": user_id})["user"]

    def conversation_info(self, channel: str) -> dict:
        return self.call("conversations.info", data={"channel": channel})["channel"]

    def get_message(self, channel: str, ts: str) -> dict | None:
        messages = self.call(
            "conversations.history", data={"channel": channel, "latest": ts, "inclusive": "true", "limit": 1}
        ).get("messages", [])
        return messages[0] if messages and messages[0].get("ts") == ts else None

    def join_channel(self, channel: str) -> dict:
        return self.call("conversations.join", data={"channel": channel})
