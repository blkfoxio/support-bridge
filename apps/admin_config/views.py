"""Admin/config API views — stub implementations."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from common.auth.backends import ApiKeyAuthentication

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
    )
    def get(self, request):
        return NOT_IMPLEMENTED
