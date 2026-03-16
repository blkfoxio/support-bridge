"""Seed the database with default queues and SLA policies."""

from django.core.management.base import BaseCommand

from apps.queues.models import Queue, SlaPolicy


SEED_QUEUES = [
    {
        "key": "soc-triage",
        "name": "SOC Triage",
        "priority_order": 100,
        "sla_first_response": 300,
        "sla_resolution": 3600,
    },
    {
        "key": "incident-response",
        "name": "Incident Response",
        "priority_order": 10,
        "sla_first_response": 120,
        "sla_resolution": 1800,
    },
    {
        "key": "billing-support",
        "name": "Billing Support",
        "priority_order": 50,
        "sla_first_response": 600,
        "sla_resolution": 7200,
    },
    {
        "key": "enterprise-soc",
        "name": "Enterprise SOC",
        "priority_order": 20,
        "sla_first_response": 180,
        "sla_resolution": 3600,
    },
]


class Command(BaseCommand):
    help = "Seed default queues and SLA policies"

    def handle(self, *args, **options):
        for queue_data in SEED_QUEUES:
            queue, created = Queue.objects.get_or_create(
                key=queue_data["key"],
                defaults={
                    "name": queue_data["name"],
                    "priority_order": queue_data["priority_order"],
                },
            )
            action = "Created" if created else "Already exists"
            self.stdout.write(f"  {action}: Queue '{queue.key}'")

            SlaPolicy.objects.get_or_create(
                queue=queue,
                active=True,
                defaults={
                    "first_response_seconds": queue_data["sla_first_response"],
                    "resolution_seconds": queue_data["sla_resolution"],
                },
            )

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(SEED_QUEUES)} queues with SLA policies"))
