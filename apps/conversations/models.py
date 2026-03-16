import uuid

from django.db import models


class ConversationStatus(models.TextChoices):
    NEW = "new", "New"
    QUEUED = "queued", "Queued"
    ASSIGNED = "assigned", "Assigned"
    WAITING_CUSTOMER = "waiting_customer", "Waiting on Customer"
    WAITING_SOC = "waiting_soc", "Waiting on SOC"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class SourceChannel(models.TextChoices):
    MOBILE_IOS = "mobile_ios", "iOS Mobile App"
    MOBILE_ANDROID = "mobile_android", "Android Mobile App"
    WEB = "web", "Web"


class Conversation(models.Model):
    """A customer support conversation — the central domain object."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Customer identity
    customer_org_id = models.CharField(max_length=100, db_index=True)
    customer_org_name = models.CharField(max_length=255, default="", blank=True)
    customer_user_id = models.CharField(max_length=255)
    customer_name = models.CharField(max_length=255, default="", blank=True)
    customer_email = models.CharField(max_length=255, default="", blank=True)

    # Classification
    source_channel = models.CharField(max_length=20, choices=SourceChannel.choices, default=SourceChannel.MOBILE_IOS)
    status = models.CharField(max_length=20, choices=ConversationStatus.choices, default=ConversationStatus.NEW)
    priority = models.CharField(max_length=20, default="normal", blank=True)
    severity = models.CharField(max_length=20, default="", blank=True)
    issue_category = models.CharField(max_length=100, default="", blank=True)
    tier = models.CharField(max_length=50, default="", blank=True)

    # Queue and assignment
    queue = models.ForeignKey("queues.Queue", on_delete=models.PROTECT, related_name="conversations")
    assigned_analyst = models.ForeignKey(
        "queues.AnalystProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="conversations"
    )

    # Roam integration
    roam_thread_key = models.CharField(max_length=255, db_index=True, help_text="threadKey used in Roam API calls")

    # Timestamps
    opened_at = models.DateTimeField(auto_now_add=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-opened_at"]
        indexes = [
            models.Index(fields=["queue", "status"], name="idx_conv_queue_status"),
            models.Index(fields=["customer_org_id", "customer_user_id"], name="idx_conv_customer"),
        ]

    def __str__(self):
        return f"Conversation {self.id} ({self.status})"


class Assignment(models.Model):
    """Tracks analyst assignment history for a conversation."""

    id = models.BigAutoField(primary_key=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="assignments")
    analyst = models.ForeignKey("queues.AnalystProfile", on_delete=models.CASCADE, related_name="assignments")
    assigned_by = models.CharField(max_length=255, help_text="ID of user who made the assignment")
    reason = models.CharField(max_length=255, default="", blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.analyst.display_name} → Conversation {self.conversation_id}"


class Tag(models.Model):
    """Reusable tag for conversation disposition and reporting."""

    id = models.BigAutoField(primary_key=True)
    key = models.SlugField(max_length=100, unique=True)
    label = models.CharField(max_length=200)

    def __str__(self):
        return self.label


class ConversationTag(models.Model):
    """Links a tag to a conversation."""

    id = models.BigAutoField(primary_key=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="conversation_tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="conversation_tags")
    applied_by = models.CharField(max_length=255, default="")
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["conversation", "tag"], name="unique_conversation_tag"),
        ]

    def __str__(self):
        return f"{self.tag.key} on {self.conversation_id}"
