import factory

from .models import AnalystProfile, Queue, QueueGroupMapping, SlaPolicy


class QueueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Queue
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda n: f"queue-{n}")
    name = factory.LazyAttribute(lambda o: o.key.replace("-", " ").title())
    active = True
    priority_order = 100


class QueueGroupMappingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = QueueGroupMapping

    queue = factory.SubFactory(QueueFactory)
    roam_group_id = factory.Sequence(lambda n: f"roam-group-{n}")
    roam_group_name = factory.LazyAttribute(lambda o: f"Roam {o.queue.name}")
    active = True


class AnalystProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnalystProfile
        django_get_or_create = ("external_user_id",)

    external_user_id = factory.Sequence(lambda n: f"analyst-{n}")
    display_name = factory.Faker("name")
    email = factory.Faker("email")
    active = True


class SlaPolicyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SlaPolicy

    queue = factory.SubFactory(QueueFactory)
    first_response_seconds = 300
    resolution_seconds = 3600
    active = True
