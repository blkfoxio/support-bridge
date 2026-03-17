"""Serializers for the admin/config API."""

from rest_framework import serializers


class RoutingRuleSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField()
    active = serializers.BooleanField()
    match_json = serializers.JSONField()
    target_queue_key = serializers.CharField(source="target_queue.key")
    priority = serializers.IntegerField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class CreateRoutingRuleRequestSerializer(serializers.Serializer):
    name = serializers.CharField()
    match_json = serializers.JSONField()
    target_queue_key = serializers.CharField(help_text="Key of the target queue")
    priority = serializers.IntegerField()
    active = serializers.BooleanField(default=True)


class UpdateRoutingRuleRequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    match_json = serializers.JSONField(required=False)
    target_queue_key = serializers.CharField(required=False)
    priority = serializers.IntegerField(required=False)
    active = serializers.BooleanField(required=False)


class QueueGroupMappingSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    queue_key = serializers.CharField(source="queue.key")
    roam_group_id = serializers.CharField()
    roam_group_name = serializers.CharField()
    active = serializers.BooleanField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class CreateQueueGroupMappingRequestSerializer(serializers.Serializer):
    queue_key = serializers.CharField(help_text="Key of the queue to map")
    roam_group_id = serializers.CharField()
    roam_group_name = serializers.CharField(required=False, default="")
    active = serializers.BooleanField(default=True)


class UpdateQueueGroupMappingRequestSerializer(serializers.Serializer):
    roam_group_id = serializers.CharField(required=False)
    roam_group_name = serializers.CharField(required=False)
    active = serializers.BooleanField(required=False)


class AnalystListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    external_user_id = serializers.CharField()
    display_name = serializers.CharField()
    email = serializers.EmailField()
    active = serializers.BooleanField()
    default_queue_key = serializers.CharField(source="default_queue.key", allow_null=True)


class AuditEventSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    event_type = serializers.CharField()
    idempotency_key = serializers.CharField()
    source = serializers.CharField()
    conversation_id = serializers.UUIDField(allow_null=True)
    payload = serializers.JSONField()
    processed_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


# ---------------------------------------------------------------------------
# Branding config
# ---------------------------------------------------------------------------


class BrandingConfigSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    org_id = serializers.CharField(allow_null=True, required=False, default=None)
    severity_colors = serializers.JSONField(required=False, default=dict)
    header_text = serializers.CharField(required=False, default="", allow_blank=True)
    fallback_color = serializers.CharField(required=False, default="", allow_blank=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class CreateBrandingConfigRequestSerializer(serializers.Serializer):
    org_id = serializers.CharField(
        allow_null=True, required=False, default=None,
        help_text="Customer org ID. Null for deployment-wide default.",
    )
    severity_colors = serializers.JSONField(
        required=False, default=dict,
        help_text='Partial map of severity→color, e.g. {"critical": "danger"}',
    )
    header_text = serializers.CharField(
        required=False, default="", allow_blank=True,
        help_text="Header block text. Empty = use deployment default.",
    )
    fallback_color = serializers.CharField(
        required=False, default="", allow_blank=True,
        help_text="Color for unknown severity levels.",
    )


class UpdateBrandingConfigRequestSerializer(serializers.Serializer):
    severity_colors = serializers.JSONField(required=False)
    header_text = serializers.CharField(required=False, allow_blank=True)
    fallback_color = serializers.CharField(required=False, allow_blank=True)
