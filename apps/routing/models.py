from django.db import models


class RoutingRule(models.Model):
    """A rule that matches conversation attributes to a target queue."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=200)
    active = models.BooleanField(default=True)
    match_json = models.JSONField(
        help_text='Match criteria, e.g. {"field": "severity", "operator": "eq", "value": "critical"}'
    )
    target_queue = models.ForeignKey("queues.Queue", on_delete=models.CASCADE, related_name="routing_rules")
    priority = models.IntegerField(help_text="Lower number = evaluated first")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority"]

    def __str__(self):
        return f"{self.name} → {self.target_queue.key} (priority {self.priority})"
