import uuid

from django.db import models


class Queue(models.Model):
    """A support queue that maps to a Roam group."""

    id = models.BigAutoField(primary_key=True)
    key = models.SlugField(max_length=100, unique=True, help_text="Unique slug identifier (e.g. soc-triage)")
    name = models.CharField(max_length=200)
    active = models.BooleanField(default=True)
    priority_order = models.IntegerField(
        default=100, help_text="Lower number = higher priority for queue ordering"
    )
    sla_first_response_seconds = models.IntegerField(null=True, blank=True)
    sla_resolution_seconds = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority_order", "name"]

    def __str__(self):
        return self.name


class QueueGroupMapping(models.Model):
    """Maps a Queue to a Roam group for message delivery."""

    id = models.BigAutoField(primary_key=True)
    queue = models.ForeignKey(Queue, on_delete=models.CASCADE, related_name="group_mappings")
    roam_group_id = models.CharField(max_length=255, help_text="Roam group/chat ID")
    roam_group_name = models.CharField(max_length=255, blank=True, default="")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["queue", "roam_group_id"], name="unique_queue_roam_group"),
        ]

    def __str__(self):
        return f"{self.queue.key} → {self.roam_group_name or self.roam_group_id}"


class AnalystProfile(models.Model):
    """A SOC analyst who can be assigned to conversations."""

    id = models.BigAutoField(primary_key=True)
    external_user_id = models.CharField(max_length=255, unique=True, help_text="Roam user ID or external identifier")
    display_name = models.CharField(max_length=200)
    email = models.EmailField()
    active = models.BooleanField(default=True)
    default_queue = models.ForeignKey(Queue, on_delete=models.SET_NULL, null=True, blank=True, related_name="analysts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name


class SlaPolicy(models.Model):
    """SLA thresholds for a queue."""

    id = models.BigAutoField(primary_key=True)
    queue = models.ForeignKey(Queue, on_delete=models.CASCADE, related_name="sla_policies")
    first_response_seconds = models.IntegerField(help_text="Max seconds to first analyst response")
    resolution_seconds = models.IntegerField(help_text="Max seconds to resolution")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "SLA policies"

    def __str__(self):
        return f"SLA for {self.queue.key}"
