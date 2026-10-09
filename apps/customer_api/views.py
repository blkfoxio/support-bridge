"""Customer-facing API views."""

import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.conversations.models import Conversation, ConversationStatus
from apps.conversations.services import ConversationService
from apps.integrations_roam.client import RoamClient
from apps.integrations_roam.mock_client import MockRoamClient
from apps.messaging.models import Message
from common.auth.backends import CognitoJWTAuthentication, FirebaseJWTAuthentication
from common.auth.one_org import OrgVerificationUnavailableError, org_verification_enabled, user_can_access_org

from .serializers import (
    ConversationDetailSerializer,
    ConversationWithMessageSerializer,
    CreateConversationRequestSerializer,
    FeedbackRequestSerializer,
    FeedbackResponseSerializer,
    MessageSerializer,
    SendMessageRequestSerializer,
    TypingRequestSerializer,
)

logger = logging.getLogger(__name__)


def _get_roam_client():
    """Return the appropriate Roam client based on settings."""
    if settings.ROAM_API_TOKEN:
        return RoamClient(settings.ROAM_API_BASE_URL, settings.ROAM_API_TOKEN)
    return MockRoamClient()


class ConversationRootView(APIView):
    """Handles GET (list) and POST (create) on /conversations/."""

    authentication_classes = [CognitoJWTAuthentication, FirebaseJWTAuthentication]

    @extend_schema(
        tags=["Customer - Conversations"],
        responses={200: ConversationDetailSerializer(many=True)},
        summary="List conversations for the authenticated user",
        description="Returns all conversations owned by the authenticated user, ordered by most recent first.",
    )
    def get(self, request):
        conversations = (
            Conversation.objects.filter(customer_user_id=request.user.uid)
            .select_related("queue")
            .order_by("-opened_at")
        )

        # Optional status filter: ?status=queued,assigned,resolved (comma-separated)
        status_filter = request.query_params.get("status")
        if status_filter:
            statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
            valid_statuses = {c.value for c in ConversationStatus}
            statuses = [s for s in statuses if s in valid_statuses]
            if statuses:
                conversations = conversations.filter(status__in=statuses)

        return Response(ConversationDetailSerializer(conversations, many=True).data)

    @extend_schema(
        tags=["Customer - Conversations"],
        request=CreateConversationRequestSerializer,
        responses={201: ConversationWithMessageSerializer},
        summary="Create a new support conversation",
        description="Creates a conversation with an initial message. Routes to appropriate queue and posts to Roam.",
    )
    def post(self, request):
        serializer = CreateConversationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        idempotency_key = request.headers.get("Idempotency-Key", "")
        if not idempotency_key:
            return Response(
                {"error": {"code": "missing_idempotency_key", "message": "Idempotency-Key header is required", "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # The owner always comes from the verified token, never the request body.
        user_id = request.user.uid
        body_user_id = data.get("user_id")
        if body_user_id and body_user_id != user_id:
            logger.warning("Ignoring body user_id=%r that differs from token uid=%r", body_user_id, user_id)

        # Prefer the token's org claim; the body value is only trusted when the token has none.
        token_org_id = getattr(request.user, "org_id", None)
        body_org_id = data.get("org_id")
        if token_org_id and body_org_id and body_org_id != token_org_id:
            return Response(
                {
                    "error": {
                        "code": "org_mismatch",
                        "message": "org_id does not match the authenticated user's organization",
                        "status": 403,
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        org_id = token_org_id or body_org_id
        if not org_id:
            return Response(
                {"error": {"code": "missing_org_id", "message": "org_id is required", "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Confirm membership with Cyflare ONE. Fails closed if ONE can't answer.
        if org_verification_enabled():
            try:
                allowed = user_can_access_org(token=request.auth, uid=user_id, org_id=org_id)
            except OrgVerificationUnavailableError:
                logger.exception("Cyflare ONE org verification unavailable for uid=%s", user_id)
                return Response(
                    {
                        "error": {
                            "code": "org_verification_unavailable",
                            "message": "Unable to verify organization right now, please try again",
                            "status": 503,
                        }
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            if not allowed:
                return Response(
                    {
                        "error": {
                            "code": "org_forbidden",
                            "message": "You do not have access to this organization",
                            "status": 403,
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        roam_client = _get_roam_client()
        service = ConversationService(roam_client)

        conversation, message = service.create_conversation(
            org_id=org_id,
            org_name=data["org_name"],
            user_id=user_id,
            customer_name=data["customer_name"],
            customer_email=data["customer_email"],
            tier=data.get("tier", "standard"),
            issue_category=data.get("issue_category", "general"),
            severity=data.get("severity", "medium"),
            source_channel=data.get("source_channel", "mobile_ios"),
            subject=data.get("subject", ""),
            message_body=data["message"],
            idempotency_key=idempotency_key,
        )

        response_data = {
            "conversation": ConversationDetailSerializer(conversation).data,
            "message": MessageSerializer(message).data,
        }
        return Response(response_data, status=status.HTTP_201_CREATED)


class ConversationDetailView(APIView):
    authentication_classes = [CognitoJWTAuthentication, FirebaseJWTAuthentication]

    @extend_schema(
        tags=["Customer - Conversations"],
        responses={200: ConversationDetailSerializer},
        summary="Get conversation detail",
    )
    def get(self, request, conversation_id):
        try:
            conversation = Conversation.objects.select_related("queue").get(id=conversation_id)
        except Conversation.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Conversation not found", "status": 404}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if conversation.customer_user_id != request.user.uid:
            return Response(
                {"error": {"code": "forbidden", "message": "You do not own this conversation", "status": 403}},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(ConversationDetailSerializer(conversation).data)


class ConversationMessagesView(APIView):
    authentication_classes = [CognitoJWTAuthentication, FirebaseJWTAuthentication]

    @extend_schema(
        tags=["Customer - Conversations"],
        responses={200: MessageSerializer(many=True)},
        summary="List messages in a conversation",
    )
    def get(self, request, conversation_id):
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Conversation not found", "status": 404}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if conversation.customer_user_id != request.user.uid:
            return Response(
                {"error": {"code": "forbidden", "message": "You do not own this conversation", "status": 403}},
                status=status.HTTP_403_FORBIDDEN,
            )

        messages = Message.objects.filter(conversation=conversation).order_by("created_at")
        return Response(MessageSerializer(messages, many=True).data)

    @extend_schema(
        tags=["Customer - Conversations"],
        request=SendMessageRequestSerializer,
        responses={201: MessageSerializer},
        summary="Send a message to a conversation",
    )
    def post(self, request, conversation_id):
        serializer = SendMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        idempotency_key = request.headers.get("Idempotency-Key", "")
        if not idempotency_key:
            return Response(
                {"error": {"code": "missing_idempotency_key", "message": "Idempotency-Key header is required", "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        roam_client = _get_roam_client()
        service = ConversationService(roam_client)

        try:
            message = service.send_message(
                conversation_id=str(conversation_id),
                user_id=request.user.uid,
                body=serializer.validated_data["message"],
                idempotency_key=idempotency_key,
            )
        except Conversation.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Conversation not found", "status": 404}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except PermissionError:
            return Response(
                {"error": {"code": "forbidden", "message": "You do not own this conversation", "status": 403}},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValueError as e:
            return Response(
                {"error": {"code": "bad_request", "message": str(e), "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)


class ConversationTypingView(APIView):
    authentication_classes = [CognitoJWTAuthentication, FirebaseJWTAuthentication]

    @extend_schema(
        tags=["Customer - Conversations"],
        request=TypingRequestSerializer,
        responses={204: None},
        summary="Set typing indicator",
    )
    def post(self, request, conversation_id):
        return Response(
            {"error": {"code": "not_implemented", "message": "Not yet implemented", "status": 501}},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


class ConversationCloseView(APIView):
    authentication_classes = [CognitoJWTAuthentication, FirebaseJWTAuthentication]

    @extend_schema(
        tags=["Customer - Conversations"],
        responses={200: ConversationDetailSerializer},
        summary="Close a conversation",
    )
    def post(self, request, conversation_id):
        roam_client = _get_roam_client()
        service = ConversationService(roam_client)

        try:
            conversation = service.close_conversation(
                conversation_id=str(conversation_id),
                user_id=request.user.uid,
                close_reason=request.data.get("close_reason", ""),
            )
        except Conversation.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Conversation not found", "status": 404}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except PermissionError:
            return Response(
                {"error": {"code": "forbidden", "message": "You do not own this conversation", "status": 403}},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValueError as e:
            return Response(
                {"error": {"code": "bad_request", "message": str(e), "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(ConversationDetailSerializer(conversation).data)


class ConversationReopenView(APIView):
    authentication_classes = [CognitoJWTAuthentication, FirebaseJWTAuthentication]

    @extend_schema(
        tags=["Customer - Conversations"],
        responses={200: ConversationDetailSerializer},
        summary="Reopen a closed or resolved conversation",
    )
    def post(self, request, conversation_id):
        roam_client = _get_roam_client()
        service = ConversationService(roam_client)

        try:
            conversation = service.reopen_conversation(
                conversation_id=str(conversation_id),
                user_id=request.user.uid,
            )
        except Conversation.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Conversation not found", "status": 404}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except PermissionError:
            return Response(
                {"error": {"code": "forbidden", "message": "You do not own this conversation", "status": 403}},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValueError as e:
            return Response(
                {"error": {"code": "bad_request", "message": str(e), "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(ConversationDetailSerializer(conversation).data)


class ConversationFeedbackView(APIView):
    authentication_classes = [CognitoJWTAuthentication, FirebaseJWTAuthentication]

    @extend_schema(
        tags=["Customer - Conversations"],
        request=FeedbackRequestSerializer,
        responses={201: FeedbackResponseSerializer},
        summary="Submit CSAT feedback for a conversation",
    )
    def post(self, request, conversation_id):
        from apps.conversations.models import Feedback

        serializer = FeedbackRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Conversation not found", "status": 404}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if conversation.customer_user_id != request.user.uid:
            return Response(
                {"error": {"code": "forbidden", "message": "You do not own this conversation", "status": 403}},
                status=status.HTTP_403_FORBIDDEN,
            )

        if conversation.status not in (ConversationStatus.CLOSED, ConversationStatus.RESOLVED):
            return Response(
                {"error": {"code": "bad_request", "message": "Feedback can only be submitted for closed or resolved conversations", "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Feedback.objects.filter(conversation=conversation).exists():
            return Response(
                {"error": {"code": "conflict", "message": "Feedback already submitted for this conversation", "status": 409}},
                status=status.HTTP_409_CONFLICT,
            )

        feedback = Feedback.objects.create(
            conversation=conversation,
            customer_user_id=request.user.uid,
            rating=serializer.validated_data["rating"],
        )

        return Response(FeedbackResponseSerializer(feedback).data, status=status.HTTP_201_CREATED)
