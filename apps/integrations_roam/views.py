"""Webhook views for Roam chat events."""

import hashlib
import hmac
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .webhook_service import WebhookService

logger = logging.getLogger(__name__)


def _verify_signature(request: Request) -> bool:
    """Verify HMAC signature if ROAM_WEBHOOK_SECRET is configured.

    Returns True if signature is valid or if no secret is configured.
    """
    secret = getattr(settings, "ROAM_WEBHOOK_SECRET", "")
    if not secret:
        return True  # No verification during early development

    signature = request.headers.get("X-Roam-Signature", "")
    if not signature:
        logger.warning("Missing X-Roam-Signature header on webhook request")
        return False

    body = request.body if hasattr(request, "body") else b""
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


class RoamChatMessageWebhookView(APIView):
    """Ingest chat message events from Roam.

    POST /webhooks/roam/chat-message

    Always returns 200 to acknowledge receipt — webhook receivers must not
    return errors to avoid Roam retrying and losing events.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        if not _verify_signature(request):
            return Response(
                {"status": "error", "reason": "invalid_signature"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            service = WebhookService()
            message = service.handle_chat_message(request.data or {})

            if message:
                return Response(
                    {"status": "ok", "message_id": str(message.id)},
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"status": "ignored"},
                status=status.HTTP_200_OK,
            )
        except Exception:
            logger.exception("Unhandled error processing chat-message webhook")
            # Still return 200 — we persisted the raw payload in the service
            return Response(
                {"status": "error", "reason": "processing_failed"},
                status=status.HTTP_200_OK,
            )


class RoamReactionWebhookView(APIView):
    """Ingest reaction events from Roam.

    POST /webhooks/roam/reaction
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        if not _verify_signature(request):
            return Response(
                {"status": "error", "reason": "invalid_signature"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            service = WebhookService()
            service.handle_reaction(request.data or {})
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Unhandled error processing reaction webhook")
            return Response(
                {"status": "error", "reason": "processing_failed"},
                status=status.HTTP_200_OK,
            )
