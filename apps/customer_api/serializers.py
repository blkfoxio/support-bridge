"""Serializers for the customer-facing API."""

import re

from rest_framework import serializers

_UUID_RE = re.compile(r'^[A-Za-z]?-?[0-9a-f]{8}-[0-9a-f]{4}-', re.IGNORECASE)


class CreateConversationRequestSerializer(serializers.Serializer):
    """Request body for creating a new support conversation."""

    org_id = serializers.CharField(help_text="Customer organization ID")
    org_name = serializers.CharField(help_text="Customer organization name")
    user_id = serializers.CharField(help_text="Customer user ID")
    customer_name = serializers.CharField(help_text="Customer display name")
    customer_email = serializers.EmailField(help_text="Customer email address")
    tier = serializers.CharField(required=False, default="standard", help_text="Customer tier (e.g. enterprise)")
    issue_category = serializers.CharField(required=False, default="general", help_text="Issue category")
    severity = serializers.CharField(required=False, default="medium", help_text="Issue severity")
    source_channel = serializers.ChoiceField(
        choices=["mobile_ios", "mobile_android", "web"], default="mobile_ios"
    )
    subject = serializers.CharField(required=False, default="", help_text="Short subject line for the conversation")
    message = serializers.CharField(help_text="Initial message body")


class SendMessageRequestSerializer(serializers.Serializer):
    """Request body for sending a message to an existing conversation."""

    message = serializers.CharField(help_text="Message body")


class TypingRequestSerializer(serializers.Serializer):
    """Request body for typing indicator."""

    is_typing = serializers.BooleanField(default=True)


class MessageSerializer(serializers.Serializer):
    """Response serializer for a single message."""

    id = serializers.UUIDField()
    conversation_id = serializers.UUIDField()
    actor_type = serializers.CharField()
    actor_id = serializers.CharField()
    sender_name = serializers.SerializerMethodField()
    direction = serializers.CharField()
    body_plain = serializers.CharField()
    message_type = serializers.CharField()
    created_at = serializers.DateTimeField()

    def get_sender_name(self, obj):
        """Derive a display name from metadata or actor_id."""
        metadata = getattr(obj, "metadata", {}) or {}
        name = metadata.get("roam_sender_name") or metadata.get("customer_name") or ""
        if name and not _UUID_RE.match(name):
            return name
        if obj.actor_type == "analyst":
            return "Cyflare Support"
        return name or obj.actor_id


class ConversationDetailSerializer(serializers.Serializer):
    """Response serializer for conversation detail."""

    id = serializers.UUIDField()
    customer_org_id = serializers.CharField()
    customer_org_name = serializers.CharField()
    customer_name = serializers.CharField()
    customer_email = serializers.CharField()
    subject = serializers.CharField()
    status = serializers.CharField()
    severity = serializers.CharField()
    issue_category = serializers.CharField()
    tier = serializers.CharField()
    queue_key = serializers.CharField(source="queue.key")
    roam_thread_key = serializers.CharField()
    opened_at = serializers.DateTimeField()
    assigned_at = serializers.DateTimeField(allow_null=True)
    first_response_at = serializers.DateTimeField(allow_null=True)
    resolved_at = serializers.DateTimeField(allow_null=True)
    closed_at = serializers.DateTimeField(allow_null=True)
    last_message_at = serializers.DateTimeField(allow_null=True)


class ConversationWithMessageSerializer(serializers.Serializer):
    """Response for create conversation — includes the initial message."""

    conversation = ConversationDetailSerializer()
    message = MessageSerializer()


class FeedbackRequestSerializer(serializers.Serializer):
    """Request body for submitting CSAT feedback."""

    rating = serializers.IntegerField(
        min_value=1, max_value=3,
        help_text="1 = Bad, 2 = OK, 3 = Great",
    )


class FeedbackResponseSerializer(serializers.Serializer):
    """Response for feedback submission."""

    id = serializers.IntegerField()
    conversation_id = serializers.UUIDField()
    rating = serializers.IntegerField()
    created_at = serializers.DateTimeField()
