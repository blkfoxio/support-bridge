"""Celery tasks for the Slack integration."""

import logging

from celery import shared_task

from apps.messaging.models import Message

from .client import SlackRateLimitError
from .inbound import handle_event
from .outbound import post_to_slack

logger = logging.getLogger(__name__)


@shared_task(name="slack.process_event", bind=True, max_retries=0)
def process_slack_event(self, payload: dict) -> None:
    handle_event(payload)


@shared_task(name="slack.deliver_message", bind=True, max_retries=3, default_retry_delay=5)
def deliver_to_slack(self, message_id: str, sender_name: str) -> None:
    message = Message.objects.filter(id=message_id).first()
    if not message:
        return
    try:
        post_to_slack(message, sender_name)
    except SlackRateLimitError as exc:
        raise self.retry(exc=exc) from exc
