import factory

from apps.queues.factories import QueueFactory

from .models import RoutingRule


class RoutingRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RoutingRule

    name = factory.Sequence(lambda n: f"Rule {n}")
    active = True
    match_json = {"field": "severity", "operator": "eq", "value": "critical"}
    target_queue = factory.SubFactory(QueueFactory)
    priority = factory.Sequence(lambda n: (n + 1) * 10)
