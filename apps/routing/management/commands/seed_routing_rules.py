"""Seed the database with default routing rules."""

from django.core.management.base import BaseCommand

from apps.queues.models import Queue
from apps.routing.models import RoutingRule


SEED_RULES = [
    {
        "name": "Critical severity → Incident Response",
        "match_json": {"field": "severity", "operator": "eq", "value": "critical"},
        "target_queue_key": "incident-response",
        "priority": 10,
    },
    {
        "name": "Billing category → Billing Support",
        "match_json": {"field": "issue_category", "operator": "eq", "value": "billing"},
        "target_queue_key": "billing-support",
        "priority": 20,
    },
    {
        "name": "Enterprise tier → Enterprise SOC",
        "match_json": {"field": "tier", "operator": "eq", "value": "enterprise"},
        "target_queue_key": "enterprise-soc",
        "priority": 30,
    },
]


class Command(BaseCommand):
    help = "Seed default routing rules (run seed_queues first)"

    def handle(self, *args, **options):
        for rule_data in SEED_RULES:
            try:
                target_queue = Queue.objects.get(key=rule_data["target_queue_key"])
            except Queue.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f"Queue '{rule_data['target_queue_key']}' not found. Run seed_queues first.")
                )
                continue

            rule, created = RoutingRule.objects.get_or_create(
                name=rule_data["name"],
                defaults={
                    "match_json": rule_data["match_json"],
                    "target_queue": target_queue,
                    "priority": rule_data["priority"],
                },
            )
            action = "Created" if created else "Already exists"
            self.stdout.write(f"  {action}: {rule.name}")

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(SEED_RULES)} routing rules"))
