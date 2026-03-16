import factory

from apps.conversations.factories import ConversationFactory

from .models import ActorType, Message, MessageDirection, MessageSource, MessageType


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Message

    conversation = factory.SubFactory(ConversationFactory)
    actor_type = ActorType.CUSTOMER
    actor_id = factory.Sequence(lambda n: f"actor-{n}")
    direction = MessageDirection.INBOUND
    source = MessageSource.CUSTOMER_API
    body_plain = factory.Faker("paragraph")
    message_type = MessageType.TEXT
