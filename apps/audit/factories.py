import factory

from .models import EventLog


class EventLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EventLog

    event_type = "conversation.created"
    idempotency_key = factory.Sequence(lambda n: f"evt-{n}")
    source = "customer_api"
    payload = factory.LazyFunction(dict)
