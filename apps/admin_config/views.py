"""Admin/config API views — stub implementations."""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, OpenApiParameter

from common.auth.backends import ApiKeyAuthentication
from apps.audit.models import EventLog

logger = logging.getLogger(__name__)

from .serializers import (
    AnalystListSerializer,
    AuditEventSerializer,
    CreateQueueGroupMappingRequestSerializer,
    CreateRoutingRuleRequestSerializer,
    QueueGroupMappingSerializer,
    RoutingRuleSerializer,
    UpdateQueueGroupMappingRequestSerializer,
    UpdateRoutingRuleRequestSerializer,
)

NOT_IMPLEMENTED = Response(
    {"error": {"code": "not_implemented", "message": "Not yet implemented", "status": 501}},
    status=status.HTTP_501_NOT_IMPLEMENTED,
)


class RoutingRuleListView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Admin - Config"], responses={200: RoutingRuleSerializer(many=True)}, summary="List routing rules"
    )
    def get(self, request):
        return NOT_IMPLEMENTED

    @extend_schema(
        tags=["Admin - Config"],
        request=CreateRoutingRuleRequestSerializer,
        responses={201: RoutingRuleSerializer},
        summary="Create a routing rule",
    )
    def post(self, request):
        return NOT_IMPLEMENTED


class RoutingRuleDetailView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Admin - Config"],
        request=UpdateRoutingRuleRequestSerializer,
        responses={200: RoutingRuleSerializer},
        summary="Update a routing rule",
    )
    def patch(self, request, rule_id):
        return NOT_IMPLEMENTED


class QueueGroupMappingListView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Admin - Config"],
        responses={200: QueueGroupMappingSerializer(many=True)},
        summary="List queue-group mappings",
    )
    def get(self, request):
        return NOT_IMPLEMENTED

    @extend_schema(
        tags=["Admin - Config"],
        request=CreateQueueGroupMappingRequestSerializer,
        responses={201: QueueGroupMappingSerializer},
        summary="Create a queue-group mapping",
    )
    def post(self, request):
        return NOT_IMPLEMENTED


class QueueGroupMappingDetailView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Admin - Config"],
        request=UpdateQueueGroupMappingRequestSerializer,
        responses={200: QueueGroupMappingSerializer},
        summary="Update a queue-group mapping",
    )
    def patch(self, request, mapping_id):
        return NOT_IMPLEMENTED


class AnalystListView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Admin - Config"], responses={200: AnalystListSerializer(many=True)}, summary="List analyst profiles"
    )
    def get(self, request):
        return NOT_IMPLEMENTED


class AuditEventListView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Admin - Audit"],
        responses={200: AuditEventSerializer(many=True)},
        summary="List audit events (filterable by conversation_id, source, event_type, date range)",
        parameters=[
            OpenApiParameter(name="conversation_id", type=str, description="Filter by conversation UUID", required=False),
            OpenApiParameter(name="source", type=str, description="Filter by event source", required=False),
            OpenApiParameter(name="event_type", type=str, description="Filter by event type", required=False),
            OpenApiParameter(name="created_after", type=str, description="ISO datetime lower bound", required=False),
            OpenApiParameter(name="created_before", type=str, description="ISO datetime upper bound", required=False),
            OpenApiParameter(name="limit", type=int, description="Max results (default 50, max 200)", required=False),
            OpenApiParameter(name="offset", type=int, description="Offset for pagination", required=False),
        ],
    )
    def get(self, request):
        logger.info("audit_event_list", extra={"params": dict(request.query_params)})
        qs = EventLog.objects.all()

        # Apply filters
        conversation_id = request.query_params.get("conversation_id")
        if conversation_id:
            qs = qs.filter(conversation_id=conversation_id)

        source = request.query_params.get("source")
        if source:
            qs = qs.filter(source=source)

        event_type = request.query_params.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)

        created_after = request.query_params.get("created_after")
        if created_after:
            qs = qs.filter(created_at__gte=created_after)

        created_before = request.query_params.get("created_before")
        if created_before:
            qs = qs.filter(created_at__lte=created_before)

        total = qs.count()

        # Pagination
        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
            offset = int(request.query_params.get("offset", 0))
        except (ValueError, TypeError):
            limit, offset = 50, 0

        events = qs.order_by("-created_at")[offset : offset + limit]
        serializer = AuditEventSerializer(events, many=True)

        return Response({
            "results": serializer.data,
            "total": total,
            "limit": limit,
            "offset": offset,
        })
