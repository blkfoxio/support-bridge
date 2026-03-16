from django.urls import path

from . import views
from .stream_views import customer_sse_stream

app_name = "customer_api"

urlpatterns = [
    path("conversations/", views.ConversationRootView.as_view(), name="conversations"),
    path("conversations/<uuid:conversation_id>/", views.ConversationDetailView.as_view(), name="conversation-detail"),
    path("conversations/<uuid:conversation_id>/messages/", views.ConversationMessagesView.as_view(), name="conversation-messages"),
    path("conversations/<uuid:conversation_id>/typing/", views.ConversationTypingView.as_view(), name="conversation-typing"),
    path("conversations/<uuid:conversation_id>/close/", views.ConversationCloseView.as_view(), name="conversation-close"),
    path("conversations/<uuid:conversation_id>/reopen/", views.ConversationReopenView.as_view(), name="conversation-reopen"),
    path("stream/", customer_sse_stream, name="customer-stream"),
]
