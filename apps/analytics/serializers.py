"""Serializers for analytics dashboard endpoints."""

from rest_framework import serializers


class QueueDepthSerializer(serializers.Serializer):
    queue_key = serializers.CharField()
    count = serializers.IntegerField()


class HourlyVolumeSerializer(serializers.Serializer):
    hour = serializers.CharField(help_text="ISO 8601 datetime for the hour bucket")
    count = serializers.IntegerField()


class AnalystHandledSerializer(serializers.Serializer):
    analyst_name = serializers.CharField()
    analyst_id = serializers.CharField()
    handled_count = serializers.IntegerField()


class DashboardKPISerializer(serializers.Serializer):
    queue_depths = QueueDepthSerializer(many=True)
    hourly_volume = HourlyVolumeSerializer(many=True)
    reopen_rate = serializers.FloatField(allow_null=True)
    period = serializers.CharField()
