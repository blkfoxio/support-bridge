"""Serializers for the ops/internal API."""

from rest_framework import serializers


class QueueListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    key = serializers.CharField()
    name = serializers.CharField()
    active = serializers.BooleanField()
    priority_order = serializers.IntegerField()
    open_count = serializers.IntegerField(help_text="Number of open conversations in this queue")


class QueueDetailSerializer(QueueListSerializer):
    sla_first_response_seconds = serializers.IntegerField(allow_null=True)
    sla_resolution_seconds = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class QueueMetricsSerializer(serializers.Serializer):
    queue_key = serializers.CharField()
    queue_depth = serializers.IntegerField()
    median_first_response_seconds = serializers.FloatField(allow_null=True)
    median_resolution_seconds = serializers.FloatField(allow_null=True)
    transfer_rate = serializers.FloatField(allow_null=True)
    sla_breach_count = serializers.IntegerField()
    period = serializers.CharField()


class OpsConversationListSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    customer_name = serializers.CharField()
    customer_org_name = serializers.CharField()
    customer_email = serializers.CharField()
    status = serializers.CharField()
    severity = serializers.CharField()
    tier = serializers.CharField()
    queue_key = serializers.CharField(source="queue.key")
    assigned_analyst_name = serializers.CharField(source="assigned_analyst.display_name", allow_null=True)
    opened_at = serializers.DateTimeField()
    last_message_at = serializers.DateTimeField(allow_null=True)


class OpsConversationDetailSerializer(OpsConversationListSerializer):
    customer_org_id = serializers.CharField()
    customer_user_id = serializers.CharField()
    issue_category = serializers.CharField()
    source_channel = serializers.CharField()
    roam_thread_key = serializers.CharField()
    assigned_at = serializers.DateTimeField(allow_null=True)
    first_response_at = serializers.DateTimeField(allow_null=True)
    resolved_at = serializers.DateTimeField(allow_null=True)
    closed_at = serializers.DateTimeField(allow_null=True)


class ClaimRequestSerializer(serializers.Serializer):
    analyst_id = serializers.CharField(help_text="External user ID of the claiming analyst")


class AssignRequestSerializer(serializers.Serializer):
    analyst_id = serializers.CharField(help_text="External user ID of the analyst to assign")
    reason = serializers.CharField(required=False, default="")


class TransferRequestSerializer(serializers.Serializer):
    target_queue_key = serializers.CharField(help_text="Key of the queue to transfer to")
    reason = serializers.CharField(required=False, default="")


class ResolveRequestSerializer(serializers.Serializer):
    resolution_note = serializers.CharField(required=False, default="")


class CloseRequestSerializer(serializers.Serializer):
    close_reason = serializers.CharField(required=False, default="")


class TagApplyRequestSerializer(serializers.Serializer):
    tags = serializers.ListField(child=serializers.CharField(), help_text="List of tag keys to apply")


class TranscriptMessageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    actor_type = serializers.CharField()
    actor_id = serializers.CharField()
    body_plain = serializers.CharField()
    message_type = serializers.CharField()
    created_at = serializers.DateTimeField()


class TranscriptSerializer(serializers.Serializer):
    conversation = OpsConversationDetailSerializer()
    messages = TranscriptMessageSerializer(many=True)
    assignment_history = serializers.ListField(child=serializers.DictField())
    tags = serializers.ListField(child=serializers.CharField())
