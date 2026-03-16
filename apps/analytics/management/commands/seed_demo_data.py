"""Generate realistic demo data for analytics testing."""

import random
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.audit.models import EventLog
from apps.conversations.models import (
    Assignment,
    Conversation,
    ConversationStatus,
    ConversationTag,
    SourceChannel,
    Tag,
)
from apps.messaging.models import ActorType, Message, MessageDirection, MessageSource, MessageType
from apps.queues.models import AnalystProfile, Queue


QUEUE_DEFS = [
    {"key": "soc-triage", "name": "SOC Triage", "priority_order": 10, "sla_fr": 300, "sla_res": 3600},
    {"key": "incident-response", "name": "Incident Response", "priority_order": 1, "sla_fr": 120, "sla_res": 1800},
    {"key": "billing-support", "name": "Billing Support", "priority_order": 50, "sla_fr": 600, "sla_res": 7200},
    {"key": "enterprise-soc", "name": "Enterprise SOC", "priority_order": 5, "sla_fr": 180, "sla_res": 2400},
]

ANALYST_DEFS = [
    {"name": "Alex Chen", "email": "alex.chen@cyflare.com"},
    {"name": "Jordan Park", "email": "jordan.park@cyflare.com"},
    {"name": "Morgan Davis", "email": "morgan.davis@cyflare.com"},
    {"name": "Riley Kim", "email": "riley.kim@cyflare.com"},
    {"name": "Casey Brooks", "email": "casey.brooks@cyflare.com"},
    {"name": "Drew Martinez", "email": "drew.martinez@cyflare.com"},
]

TAG_DEFS = [
    ("resolved-fixed", "Resolved — Fixed"),
    ("resolved-workaround", "Resolved — Workaround"),
    ("resolved-no-action", "Resolved — No Action Needed"),
    ("escalated", "Escalated"),
    ("false-positive", "False Positive"),
]

CATEGORIES = ["incident", "access_issue", "billing", "configuration", "general"]
SEVERITIES = ["critical", "high", "medium", "low"]
TIERS = ["enterprise", "professional", "standard"]

CUSTOMER_MESSAGES = [
    "We are seeing failed logins across multiple tenants.",
    "Our firewall rules stopped applying after the last update.",
    "Need help understanding the latest threat report.",
    "Getting 403 errors on the API endpoint.",
    "Can you check the billing for this month? Looks incorrect.",
    "MFA stopped working for our admin accounts.",
    "Seeing unusual traffic patterns from an external IP.",
    "Need to add a new user to our SOC dashboard.",
    "Alert fatigue — too many low-severity notifications.",
    "VPN connection keeps dropping for remote users.",
]

ANALYST_REPLIES = [
    "We are investigating now. I'll update you shortly.",
    "I can see the issue in our logs. Working on a fix.",
    "This looks like a configuration issue. Let me check.",
    "I've escalated this to our senior team for review.",
    "The fix has been applied. Can you verify on your end?",
    "I've updated the rules. Please test when ready.",
    "This is a known issue. We have a patch rolling out.",
    "I'll need some additional information to proceed.",
]


class Command(BaseCommand):
    help = "Seed demo data for analytics testing"

    def add_arguments(self, parser):
        parser.add_argument("--conversations", type=int, default=60, help="Number of conversations to create")
        parser.add_argument("--days", type=int, default=7, help="Spread conversations over N days")
        parser.add_argument("--clear", action="store_true", help="Clear existing demo data first")

    def handle(self, *args, **options):
        num_conversations = options["conversations"]
        num_days = options["days"]

        if options["clear"]:
            self.stdout.write("Clearing existing data...")
            Message.objects.all().delete()
            Assignment.objects.all().delete()
            ConversationTag.objects.all().delete()
            EventLog.objects.all().delete()
            Conversation.objects.all().delete()
            AnalystProfile.objects.all().delete()
            Tag.objects.all().delete()
            Queue.objects.all().delete()

        # Create queues
        queues = []
        for qd in QUEUE_DEFS:
            q, _ = Queue.objects.get_or_create(
                key=qd["key"],
                defaults={
                    "name": qd["name"],
                    "priority_order": qd["priority_order"],
                    "sla_first_response_seconds": qd["sla_fr"],
                    "sla_resolution_seconds": qd["sla_res"],
                },
            )
            queues.append(q)
        self.stdout.write(f"  Queues: {len(queues)}")

        # Create analysts
        analysts = []
        for ad in ANALYST_DEFS:
            ext_id = ad["email"].split("@")[0].replace(".", "-")
            a, _ = AnalystProfile.objects.get_or_create(
                external_user_id=ext_id,
                defaults={
                    "display_name": ad["name"],
                    "email": ad["email"],
                    "default_queue": random.choice(queues),
                },
            )
            analysts.append(a)
        self.stdout.write(f"  Analysts: {len(analysts)}")

        # Create tags
        tags = []
        for key, label in TAG_DEFS:
            t, _ = Tag.objects.get_or_create(key=key, defaults={"label": label})
            tags.append(t)
        self.stdout.write(f"  Tags: {len(tags)}")

        # Create conversations
        now = timezone.now()
        transferred_count = 0
        reopened_count = 0
        sla_breach_count = 0

        for i in range(num_conversations):
            # Random time in the past N days, weighted toward business hours
            days_ago = random.uniform(0, num_days)
            hour_offset = random.gauss(14, 3)  # Peak around 2 PM
            hour_offset = max(6, min(22, hour_offset))
            opened_at = now - timedelta(days=days_ago)
            opened_at = opened_at.replace(hour=int(hour_offset), minute=random.randint(0, 59))

            queue = random.choice(queues)
            severity = random.choice(SEVERITIES)
            category = random.choice(CATEGORIES)
            tier = random.choice(TIERS)

            # Determine conversation status and timings
            status_roll = random.random()
            if status_roll < 0.15:
                conv_status = ConversationStatus.NEW
            elif status_roll < 0.25:
                conv_status = ConversationStatus.QUEUED
            elif status_roll < 0.45:
                conv_status = ConversationStatus.ASSIGNED
            elif status_roll < 0.55:
                conv_status = ConversationStatus.WAITING_CUSTOMER
            elif status_roll < 0.65:
                conv_status = ConversationStatus.WAITING_SOC
            elif status_roll < 0.85:
                conv_status = ConversationStatus.RESOLVED
            else:
                conv_status = ConversationStatus.CLOSED

            # Generate timestamps based on status
            assigned_at = None
            first_response_at = None
            resolved_at = None
            closed_at = None
            analyst = None

            if conv_status not in (ConversationStatus.NEW, ConversationStatus.QUEUED):
                analyst = random.choice(analysts)
                # Time to assignment: 30s to 15min
                assign_delta = timedelta(seconds=random.uniform(30, 900))
                assigned_at = opened_at + assign_delta

                # ~10% breach SLA on first response
                sla_fr = queue.sla_first_response_seconds or 300
                if random.random() < 0.10:
                    fr_delta = timedelta(seconds=sla_fr + random.uniform(60, sla_fr))
                    sla_breach_count += 1
                else:
                    fr_delta = timedelta(seconds=random.uniform(30, sla_fr * 0.8))
                first_response_at = opened_at + fr_delta

            if conv_status in (ConversationStatus.RESOLVED, ConversationStatus.CLOSED):
                sla_res = queue.sla_resolution_seconds or 3600
                if random.random() < 0.08:
                    res_delta = timedelta(seconds=sla_res + random.uniform(300, sla_res))
                else:
                    res_delta = timedelta(seconds=random.uniform(300, sla_res * 0.8))
                resolved_at = opened_at + res_delta

            if conv_status == ConversationStatus.CLOSED:
                closed_at = (resolved_at or opened_at) + timedelta(minutes=random.randint(1, 60))

            conv_id = uuid.uuid4()
            conv = Conversation(
                id=conv_id,
                customer_org_id=f"org_{random.randint(100, 999)}",
                customer_org_name=f"Customer Org {random.randint(1, 50)}",
                customer_user_id=f"user_{random.randint(1000, 9999)}",
                customer_name=f"User {i + 1}",
                customer_email=f"user{i + 1}@example.com",
                source_channel=SourceChannel.MOBILE_IOS,
                status=conv_status,
                priority="normal",
                severity=severity,
                issue_category=category,
                tier=tier,
                queue=queue,
                assigned_analyst=analyst,
                roam_thread_key=str(conv_id),
                assigned_at=assigned_at,
                first_response_at=first_response_at,
                resolved_at=resolved_at,
                closed_at=closed_at,
            )
            conv.save()

            # Override auto_now_add opened_at
            Conversation.objects.filter(pk=conv_id).update(opened_at=opened_at, last_message_at=opened_at)

            # Create event log for conversation creation
            EventLog.objects.create(
                event_type="conversation.created",
                idempotency_key=f"conv-created-{conv_id}",
                source="customer_api",
                conversation=conv,
                payload={"status": conv_status, "queue": queue.key},
            )

            # Create messages (2–8 per conversation)
            num_messages = random.randint(2, 8)
            msg_time = opened_at
            for m in range(num_messages):
                if m == 0:
                    # First message is always from customer
                    actor_type = ActorType.CUSTOMER
                    body = random.choice(CUSTOMER_MESSAGES)
                elif m == 1 and first_response_at:
                    actor_type = ActorType.ANALYST
                    body = random.choice(ANALYST_REPLIES)
                    msg_time = first_response_at
                else:
                    actor_type = random.choice([ActorType.CUSTOMER, ActorType.ANALYST])
                    body = random.choice(CUSTOMER_MESSAGES if actor_type == ActorType.CUSTOMER else ANALYST_REPLIES)

                msg_time = msg_time + timedelta(minutes=random.randint(1, 15))
                msg = Message(
                    conversation=conv,
                    actor_type=actor_type,
                    actor_id=analyst.external_user_id if actor_type == ActorType.ANALYST and analyst else conv.customer_user_id,
                    direction=MessageDirection.INBOUND if actor_type == ActorType.CUSTOMER else MessageDirection.OUTBOUND,
                    source=MessageSource.CUSTOMER_API if actor_type == ActorType.CUSTOMER else MessageSource.ROAM_WEBHOOK,
                    body_plain=body,
                    message_type=MessageType.TEXT,
                )
                msg.save()
                # Override created_at
                Message.objects.filter(pk=msg.pk).update(created_at=msg_time)

            # Update last_message_at
            Conversation.objects.filter(pk=conv_id).update(last_message_at=msg_time)

            # Create assignment record if assigned
            if analyst and assigned_at:
                Assignment.objects.create(
                    conversation=conv,
                    analyst=analyst,
                    assigned_by="system",
                    reason="auto-assigned",
                )

            # ~8% get transferred
            if random.random() < 0.08 and analyst:
                transferred_count += 1
                EventLog.objects.create(
                    event_type="conversation.transferred",
                    idempotency_key=f"conv-transfer-{conv_id}",
                    source="ops_api",
                    conversation=conv,
                    payload={"from_queue": queue.key, "to_queue": random.choice(queues).key},
                )

            # ~5% get reopened
            if random.random() < 0.05 and conv_status == ConversationStatus.CLOSED:
                reopened_count += 1
                EventLog.objects.create(
                    event_type="conversation.reopened",
                    idempotency_key=f"conv-reopen-{conv_id}",
                    source="customer_api",
                    conversation=conv,
                )

            # Apply tags to resolved/closed conversations
            if conv_status in (ConversationStatus.RESOLVED, ConversationStatus.CLOSED):
                tag = random.choice(tags)
                ConversationTag.objects.get_or_create(
                    conversation=conv, tag=tag, defaults={"applied_by": "system"}
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSeeded {num_conversations} conversations "
                f"({transferred_count} transferred, {reopened_count} reopened, "
                f"~{sla_breach_count} SLA breaches)"
            )
        )
