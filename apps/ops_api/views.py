"""Ops API views — stub implementations."""

import logging

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter

from common.auth.backends import ApiKeyAuthentication
from apps.analytics.services import AnalyticsService, parse_period

logger = logging.getLogger(__name__)
from apps.conversations.models import Conversation
from apps.queues.models import Queue

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
    TranscriptMessageSerializer,
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

    @extend_schema(
        tags=["Ops - Queues"],
        responses={200: QueueMetricsSerializer},
        summary="Queue KPI metrics",
        parameters=[
            OpenApiParameter(name="period", type=str, description="Time window (e.g. 1h, 6h, 24h, 7d, 30d)", required=False),
        ],
    )
    def get(self, request, queue_id):
        queue = get_object_or_404(Queue, pk=queue_id)
        period_str = request.query_params.get("period", "24h")
        try:
            period_start, period_end = parse_period(period_str)
        except ValueError:
            raise ValidationError(f"Invalid period format: {period_str}. Use e.g. '24h' or '7d'.")

        logger.info("queue_metrics", extra={"queue_id": queue_id, "period": period_str})
        depth_rows = AnalyticsService.queue_depth(queue_id=queue.pk)
        depth = depth_rows[0]["count"] if depth_rows else 0

        data = {
            "queue_key": queue.key,
            "queue_depth": depth,
            "median_first_response_seconds": AnalyticsService.median_first_response(queue.pk, period_start, period_end),
            "median_resolution_seconds": AnalyticsService.median_resolution_time(queue.pk, period_start, period_end),
            "transfer_rate": AnalyticsService.transfer_rate(queue.pk, period_start, period_end),
            "sla_breach_count": AnalyticsService.sla_breach_count(queue.pk, period_start, period_end),
            "period": period_str,
        }
        return Response(data)


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
        logger.info("transcript", extra={"conversation_id": str(conversation_id)})
        conversation = get_object_or_404(
            Conversation.objects.select_related("queue", "assigned_analyst"),
            pk=conversation_id,
        )

        conv_data = OpsConversationDetailSerializer(conversation).data

        messages = conversation.messages.order_by("created_at")
        messages_data = TranscriptMessageSerializer(messages, many=True).data

        assignments = conversation.assignments.select_related("analyst").order_by("assigned_at")
        assignment_history = [
            {
                "analyst_name": a.analyst.display_name,
                "analyst_id": a.analyst.external_user_id,
                "assigned_by": a.assigned_by,
                "reason": a.reason,
                "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
                "ended_at": a.ended_at.isoformat() if a.ended_at else None,
            }
            for a in assignments
        ]

        tags = list(
            conversation.conversation_tags.select_related("tag").values_list("tag__key", flat=True)
        )

        data = {
            "conversation": conv_data,
            "messages": messages_data,
            "assignment_history": assignment_history,
            "tags": tags,
        }
        return Response(data)
