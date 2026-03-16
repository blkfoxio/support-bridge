import uuid

from django.db import models


class ActorType(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    ANALYST = "analyst", "Analyst"
    SYSTEM = "system", "System"


class MessageDirection(models.TextChoices):
    INBOUND = "inbound", "Inbound (customer → system)"
    OUTBOUND = "outbound", "Outbound (system → customer)"


class MessageSource(models.TextChoices):
    CUSTOMER_API = "customer_api", "Customer API"
    ROAM_WEBHOOK = "roam_webhook", "Roam Webhook"
    INTERNAL = "internal", "Internal System"


class MessageType(models.TextChoices):
    TEXT = "text", "Text Message"
    SYSTEM_NOTE = "system_note", "System Note"
    STATUS = "status", "Status Update"


class Message(models.Model):
    """A single message within a conversation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        "conversations.Conversation", on_delete=models.CASCADE, related_name="messages"
    )

    # Actor
    actor_type = models.CharField(max_length=20, choices=ActorType.choices)
    actor_id = models.CharField(max_length=255, help_text="UID of the customer, analyst, or system")
    direction = models.CharField(max_length=20, choices=MessageDirection.choices)
    source = models.CharField(max_length=20, choices=MessageSource.choices)

    # External reference
    external_message_id = models.CharField(
        max_length=255, null=True, blank=True, help_text="Message ID from Roam or external system"
    )

    # Content
    body_plain = models.TextField()
    body_markdown = models.TextField(null=True, blank=True)
    message_type = models.CharField(max_length=20, choices=MessageType.choices, default=MessageType.TEXT)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    # Flexible metadata
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="idx_msg_conv_created"),
        ]

    def __str__(self):
        return f"Message {self.id} ({self.actor_type})"
