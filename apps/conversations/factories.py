import uuid

import factory
from django.utils import timezone

from apps.queues.factories import AnalystProfileFactory, QueueFactory

from .models import Assignment, Conversation, ConversationStatus, ConversationTag, SourceChannel, Tag


class ConversationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Conversation

    customer_org_id = factory.Sequence(lambda n: str(n + 1))
    customer_org_name = factory.Faker("company")
    customer_user_id = factory.Sequence(lambda n: f"user-{n}")
    customer_name = factory.Faker("name")
    customer_email = factory.Faker("email")
    source_channel = SourceChannel.MOBILE_IOS
    status = ConversationStatus.QUEUED
    severity = "medium"
    issue_category = "general"
    tier = "standard"
    queue = factory.SubFactory(QueueFactory)
    roam_thread_key = factory.LazyFunction(lambda: str(uuid.uuid4()))


class AssignmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Assignment

    conversation = factory.SubFactory(ConversationFactory)
    analyst = factory.SubFactory(AnalystProfileFactory)
    assigned_by = "system"
    reason = "auto-assigned"


class TagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tag
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda n: f"tag-{n}")
    label = factory.LazyAttribute(lambda o: o.key.replace("-", " ").title())


class ConversationTagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ConversationTag

    conversation = factory.SubFactory(ConversationFactory)
    tag = factory.SubFactory(TagFactory)
    applied_by = "system"
