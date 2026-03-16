"""SSE pub/sub infrastructure using Redis.

Provides sync publishing (for webhook handlers and services) and async
subscribing (for SSE streaming endpoints).
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field

import redis
import redis.asyncio as aioredis
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _channel_name(conversation_id: str) -> str:
    return f"conversation:{conversation_id}"


@dataclass
class SSEEvent:
    """A single server-sent event."""

    event_type: str
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    data: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = timezone.now().isoformat()

    def to_sse(self) -> str:
        """Format as an SSE text block."""
        lines = [
            f"event: {self.event_type}",
            f"id: {self.event_id}",
            f"data: {json.dumps(self.data)}",
            "",
            "",  # SSE requires double newline terminator
        ]
        return "\n".join(lines)


class SSEPublisher:
    """Synchronous Redis publisher — safe to call from Django views and services."""

    def __init__(self):
        self._redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    def publish(self, conversation_id: str, event_type: str, data: dict) -> str:
        """Publish an event to a conversation channel.

        Returns the event_id.
        """
        event = SSEEvent(event_type=event_type, data=data)
        channel = _channel_name(conversation_id)
        # Convert to plain dict manually to avoid issues with DRF's ReturnDict
        # (which subclasses OrderedDict and requires a 'serializer' kwarg).
        payload = json.dumps({
            "event_type": event.event_type,
            "event_id": event.event_id,
            "data": dict(event.data) if event.data else {},
            "timestamp": event.timestamp,
        })
        self._redis.publish(channel, payload)
        logger.debug("Published %s to %s (event_id=%s)", event_type, channel, event.event_id)
        return event.event_id


class SSESubscriber:
    """Async Redis subscriber — used by SSE streaming endpoints under ASGI."""

    def __init__(self):
        self._redis = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        self._pubsub = self._redis.pubsub()

    async def subscribe(self, conversation_id: str) -> None:
        """Subscribe to a conversation channel."""
        channel = _channel_name(conversation_id)
        await self._pubsub.subscribe(channel)
        logger.debug("Subscribed to %s", channel)

    async def listen(self):
        """Async generator yielding SSEEvent objects as they arrive."""
        async for raw_message in self._pubsub.listen():
            if raw_message["type"] != "message":
                continue
            try:
                envelope = json.loads(raw_message["data"])
                yield SSEEvent(
                    event_type=envelope.get("event_type", "unknown"),
                    event_id=envelope.get("event_id", f"evt_{uuid.uuid4().hex[:12]}"),
                    data=envelope.get("data", {}),
                    timestamp=envelope.get("timestamp", ""),
                )
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to parse SSE event from Redis: %s", raw_message["data"])
                continue

    async def close(self) -> None:
        """Unsubscribe and close the Redis connection."""
        try:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
            await self._redis.close()
        except Exception:
            logger.debug("Error closing SSE subscriber", exc_info=True)
