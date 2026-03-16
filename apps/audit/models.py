from django.db import models


class EventLog(models.Model):
    """Immutable audit log entry for traceability and idempotent processing."""

    id = models.BigAutoField(primary_key=True)
    event_type = models.CharField(max_length=100, db_index=True)
    idempotency_key = models.CharField(max_length=255, unique=True, help_text="Unique key to prevent duplicate processing")
    source = models.CharField(max_length=100, help_text="Origin of the event (e.g. customer_api, roam_webhook)")
    conversation = models.ForeignKey(
        "conversations.Conversation", on_delete=models.SET_NULL, null=True, blank=True, related_name="event_logs"
    )
    payload = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["conversation"], name="idx_eventlog_conversation"),
            models.Index(fields=["event_type", "created_at"], name="idx_eventlog_type_created"),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.idempotency_key})"
