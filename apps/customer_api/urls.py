from django.urls import path

from . import views

app_name = "customer_api"

urlpatterns = [
    path("conversations/", views.CreateConversationView.as_view(), name="create-conversation"),
    path("conversations/<uuid:conversation_id>/", views.ConversationDetailView.as_view(), name="conversation-detail"),
    path("conversations/<uuid:conversation_id>/messages/", views.ConversationMessagesView.as_view(), name="conversation-messages"),
    path("conversations/<uuid:conversation_id>/typing/", views.ConversationTypingView.as_view(), name="conversation-typing"),
    path("conversations/<uuid:conversation_id>/close/", views.ConversationCloseView.as_view(), name="conversation-close"),
    path("conversations/<uuid:conversation_id>/reopen/", views.ConversationReopenView.as_view(), name="conversation-reopen"),
]
