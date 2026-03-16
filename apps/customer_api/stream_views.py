"""SSE streaming endpoint for real-time customer conversation updates.

This is a plain async Django view (not DRF) because StreamingHttpResponse
doesn't integrate well with DRF's middleware and renderer stack.
"""

import asyncio
import json
import logging

from asgiref.sync import sync_to_async
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.conversations.models import Conversation
from common.sse import SSEEvent, SSESubscriber

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 25  # seconds


async def _verify_firebase_token(token: str):
    """Verify a Firebase ID token and return the decoded claims, or None."""
    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth

        # Ensure Firebase app is initialized
        try:
            firebase_admin.get_app()
        except ValueError:
            from django.conf import settings

            if settings.FIREBASE_SERVICE_ACCOUNT_KEY:
                import base64

                try:
                    key_data = json.loads(base64.b64decode(settings.FIREBASE_SERVICE_ACCOUNT_KEY))
                    cred = firebase_admin.credentials.Certificate(key_data)
                except Exception:
                    cred = firebase_admin.credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_KEY)
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app()

        # verify_id_token is synchronous
        decoded = await sync_to_async(firebase_auth.verify_id_token)(token)
        return decoded
    except Exception as e:
        logger.debug("Firebase token verification failed: %s", e)
        return None


def _format_sse(event: SSEEvent) -> str:
    """Format an SSEEvent as a text/event-stream block."""
    return event.to_sse()


def _heartbeat_sse() -> str:
    """Format a heartbeat event."""
    event = SSEEvent(event_type="heartbeat", data={"type": "ping"})
    return event.to_sse()


async def _event_stream(conversation_id: str):
    """Async generator that yields SSE-formatted strings.

    Subscribes to Redis pub/sub for the conversation channel and
    interleaves heartbeat events every HEARTBEAT_INTERVAL seconds.
    """
    subscriber = SSESubscriber()
    try:
        await subscriber.subscribe(conversation_id)
        listener = subscriber.listen()

        while True:
            try:
                event = await asyncio.wait_for(
                    listener.__anext__(),
                    timeout=HEARTBEAT_INTERVAL,
                )
                yield _format_sse(event)
            except asyncio.TimeoutError:
                yield _heartbeat_sse()
            except StopAsyncIteration:
                break
    except (asyncio.CancelledError, GeneratorExit):
        pass
    finally:
        await subscriber.close()


@csrf_exempt
async def customer_sse_stream(request):
    """SSE endpoint for real-time conversation updates.

    GET /api/v1/customer/stream/?conversation_id=<uuid>

    Requires Firebase Bearer token authentication. The customer can only
    subscribe to conversations they own.
    """
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    # 1. Extract and verify auth token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JsonResponse({"error": "Missing or invalid Authorization header"}, status=401)

    token = auth_header[7:]  # Strip "Bearer "
    decoded = await _verify_firebase_token(token)
    if decoded is None:
        return JsonResponse({"error": "Invalid or expired token"}, status=401)

    user_uid = decoded.get("uid", "")

    # 2. Get and validate conversation_id
    conversation_id = request.GET.get("conversation_id", "")
    if not conversation_id:
        return JsonResponse({"error": "conversation_id query parameter is required"}, status=400)

    # Look up conversation and validate ownership
    try:
        conversation = await sync_to_async(
            Conversation.objects.get
        )(id=conversation_id)
    except Conversation.DoesNotExist:
        return JsonResponse({"error": "Conversation not found"}, status=404)

    if conversation.customer_user_id != user_uid:
        return JsonResponse({"error": "Not authorized to access this conversation"}, status=403)

    # 3. Check Last-Event-ID (acknowledged but not replayed for prototype)
    last_event_id = request.headers.get("Last-Event-ID")
    if last_event_id:
        logger.debug(
            "Client reconnected with Last-Event-ID=%s for conversation=%s (replay not implemented)",
            last_event_id,
            conversation_id,
        )

    # 4. Return streaming response
    response = StreamingHttpResponse(
        _event_stream(str(conversation.id)),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
