from django.urls import path

from . import views

app_name = "integrations_roam"

urlpatterns = [
    path("chat-message", views.RoamChatMessageWebhookView.as_view(), name="chat-message-webhook"),
    path("reaction", views.RoamReactionWebhookView.as_view(), name="reaction-webhook"),
]
