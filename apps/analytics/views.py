"""Analytics dashboard views."""

import logging

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, OpenApiParameter

from common.auth.backends import ApiKeyAuthentication
from .serializers import AnalystHandledSerializer, DashboardKPISerializer, HourlyVolumeSerializer
from .services import AnalyticsService, parse_period

logger = logging.getLogger(__name__)

PERIOD_PARAM = OpenApiParameter(
    name="period", type=str, description="Time window (e.g. 1h, 6h, 24h, 7d, 30d)", required=False
)


def _parse_period(request):
    """Parse and validate the period query param. Raises ValidationError on bad input."""
    period_str = request.query_params.get("period", "24h")
    try:
        start, end = parse_period(period_str)
    except ValueError:
        raise ValidationError(f"Invalid period format: {period_str}. Use e.g. '24h' or '7d'.")
    return period_str, start, end


class DashboardKPIView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Analytics"],
        responses={200: DashboardKPISerializer},
        summary="Dashboard KPI summary",
        parameters=[PERIOD_PARAM],
    )
    def get(self, request):
        period_str, start, end = _parse_period(request)
        logger.info("dashboard_kpi", extra={"period": period_str})

        data = {
            "queue_depths": AnalyticsService.queue_depth(),
            "hourly_volume": AnalyticsService.hourly_volume(start, end),
            "reopen_rate": AnalyticsService.reopen_rate(start, end),
            "period": period_str,
        }
        return Response(data)


class HourlyVolumeView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Analytics"],
        responses={200: HourlyVolumeSerializer(many=True)},
        summary="Hourly conversation volume",
        parameters=[PERIOD_PARAM],
    )
    def get(self, request):
        period_str, start, end = _parse_period(request)
        logger.info("hourly_volume", extra={"period": period_str})
        return Response(AnalyticsService.hourly_volume(start, end))


class AnalystLeaderboardView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    @extend_schema(
        tags=["Ops - Analytics"],
        responses={200: AnalystHandledSerializer(many=True)},
        summary="Analyst handled counts",
        parameters=[PERIOD_PARAM],
    )
    def get(self, request):
        period_str, start, end = _parse_period(request)
        logger.info("analyst_leaderboard", extra={"period": period_str})
        return Response(AnalyticsService.analyst_handled_count(start, end))
