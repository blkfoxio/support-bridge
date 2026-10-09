from django.apps import AppConfig


class IntegrationsSlackConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations_slack"
    label = "integrations_slack"

    def ready(self):
        from apps.messaging.delivery import register_channel_deliverer

        from .outbound import SlackDeliverer

        register_channel_deliverer(SlackDeliverer())
