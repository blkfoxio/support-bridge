"""Ops API views — stub implementations."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from common.auth.backends import ApiKeyAuthentication

from .serializers import (
    AssignRequestSerializer,
    ClaimRequestSerializer,
    CloseRequestSerializer,
    OpsConversationDetailSerializer,
    OpsConversationListSerializer,
    QueueDetailSerializer,
    QueueListSerializer,
    QueueMetricsSerializer,
    ResolveRequestSerializer,
    TagApplyRequestSerializer,
    TranscriptSerializer,
    TransferRequestSerializer,
)

NOT_IMPLEMENTED = Response(
    {"error": {"code": "not_implemented", "message": "Not yet implemented", "status": 501}},
    status=status.HTTP_501_NOT_IMPLEMENTED,
)


class QueueListView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(tags=["Ops - Queues"], responses={200: QueueListSerializer(many=True)}, summary="List queues")
    def get(self, request):
        return NOT_IMPLEMENTED


class QueueDetailView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(tags=["Ops - Queues"], responses={200: QueueDetailSerializer}, summary="Queue detail")
    def get(self, request, queue_id):
        return NOT_IMPLEMENTED


class QueueMetricsView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(tags=["Ops - Queues"], responses={200: QueueMetricsSerializer}, summary="Queue KPI metrics")
    def get(self, request, queue_id):
        return NOT_IMPLEMENTED


class OpsConversationListView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Conversations"],
        responses={200: OpsConversationListSerializer(many=True)},
        summary="List conversations (filterable)",
    )
    def get(self, request):
        return NOT_IMPLEMENTED


class OpsConversationDetailView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Conversations"], responses={200: OpsConversationDetailSerializer}, summary="Conversation detail"
    )
    def get(self, request, conversation_id):
        return NOT_IMPLEMENTED


class ConversationClaimView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Conversations"],
        request=ClaimRequestSerializer,
        responses={200: OpsConversationDetailSerializer},
        summary="Claim a conversation",
    )
    def post(self, request, conversation_id):
        return NOT_IMPLEMENTED


class ConversationAssignView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Conversations"],
        request=AssignRequestSerializer,
        responses={200: OpsConversationDetailSerializer},
        summary="Assign conversation to analyst",
    )
    def post(self, request, conversation_id):
        return NOT_IMPLEMENTED


class ConversationTransferView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Conversations"],
        request=TransferRequestSerializer,
        responses={200: OpsConversationDetailSerializer},
        summary="Transfer conversation to another queue",
    )
    def post(self, request, conversation_id):
        return NOT_IMPLEMENTED


class ConversationResolveView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Conversations"],
        request=ResolveRequestSerializer,
        responses={200: OpsConversationDetailSerializer},
        summary="Resolve a conversation",
    )
    def post(self, request, conversation_id):
        return NOT_IMPLEMENTED


class ConversationCloseView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Conversations"],
        request=CloseRequestSerializer,
        responses={200: OpsConversationDetailSerializer},
        summary="Close a conversation",
    )
    def post(self, request, conversation_id):
        return NOT_IMPLEMENTED


class ConversationTagView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Conversations"],
        request=TagApplyRequestSerializer,
        responses={200: OpsConversationDetailSerializer},
        summary="Apply tags to a conversation",
    )
    def post(self, request, conversation_id):
        return NOT_IMPLEMENTED


class TranscriptView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Conversations"], responses={200: TranscriptSerializer}, summary="Get conversation transcript"
    )
    def get(self, request, conversation_id):
        return NOT_IMPLEMENTED
