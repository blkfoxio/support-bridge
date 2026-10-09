"""Create external identities and link them to Cyflare ONE accounts."""

import logging

from django.db import transaction
from django.utils import timezone

from apps.conversations.models import Conversation, ConversationParticipant, Feedback
from apps.messaging.models import ActorType, Message

from .models import ExternalIdentity

logger = logging.getLogger(__name__)


def upsert_identity(
    *, provider: str, team_id: str, external_user_id: str, org_id: str, email: str = "", display_name: str = ""
) -> ExternalIdentity:
    """Return the identity for this provider user, refreshing its profile fields."""
    identity, created = ExternalIdentity.objects.get_or_create(
        provider=provider,
        team_id=team_id,
        external_user_id=external_user_id,
        defaults={"org_id": org_id, "email": email, "display_name": display_name},
    )
    if not created:
        changed = {
            field: value
            for field, value in {"org_id": org_id, "email": email, "display_name": display_name}.items()
            if value and getattr(identity, field) != value
        }
        if changed:
            for field, value in changed.items():
                setattr(identity, field, value)
            identity.save(update_fields=[*changed, "updated_at"])
    return identity


@transaction.atomic
def link_identity(identity: ExternalIdentity, user_id: str) -> int:
    """Link an identity to a ONE user and move its history from the synthetic ID to the real one.

    Returns the number of conversations whose owner changed.
    """
    synthetic = identity.synthetic_user_id
    identity.linked_user_id = user_id
    identity.linked_at = timezone.now()
    identity.save(update_fields=["linked_user_id", "linked_at", "updated_at"])

    owned = Conversation.objects.filter(customer_user_id=synthetic).update(customer_user_id=user_id)

    for participant in ConversationParticipant.objects.filter(user_id=synthetic):
        already = ConversationParticipant.objects.filter(conversation_id=participant.conversation_id, user_id=user_id)
        if already.exists():
            participant.delete()
        else:
            participant.user_id = user_id
            participant.save(update_fields=["user_id"])

    Message.objects.filter(actor_type=ActorType.CUSTOMER, actor_id=synthetic).update(actor_id=user_id)
    Feedback.objects.filter(customer_user_id=synthetic).update(customer_user_id=user_id)

    logger.info("Linked %s to ONE user %s (%d conversations re-owned)", synthetic, user_id, owned)
    return owned


def auto_link_by_email(*, user_id: str, email: str, org_id: str) -> list[ExternalIdentity]:
    """Link unlinked identities in ``org_id`` whose email matches a verified ONE email; return those linked."""
    if not email:
        return []
    candidates = ExternalIdentity.objects.filter(org_id=org_id, email__iexact=email, linked_user_id__isnull=True)
    linked = []
    for identity in candidates:
        link_identity(identity, user_id)
        linked.append(identity)
    return linked
