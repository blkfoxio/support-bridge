"""Who may see and act on a conversation: its owner plus any participants."""

from django.db.models import Q, QuerySet

from .models import Conversation, ConversationParticipant


def accessible_conversations(user_id: str) -> QuerySet[Conversation]:
    participant_ids = ConversationParticipant.objects.filter(user_id=user_id).values("conversation_id")
    return Conversation.objects.filter(Q(customer_user_id=user_id) | Q(id__in=participant_ids))


def can_access(conversation: Conversation, user_id: str) -> bool:
    if conversation.customer_user_id == user_id:
        return True
    return ConversationParticipant.objects.filter(conversation=conversation, user_id=user_id).exists()
