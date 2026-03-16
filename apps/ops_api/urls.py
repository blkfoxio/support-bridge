from django.urls import path

from . import views

app_name = "ops_api"

urlpatterns = [
    # Queues
    path("queues/", views.QueueListView.as_view(), name="queue-list"),
    path("queues/<int:queue_id>/", views.QueueDetailView.as_view(), name="queue-detail"),
    path("queues/<int:queue_id>/metrics/", views.QueueMetricsView.as_view(), name="queue-metrics"),
    # Conversations
    path("conversations/", views.OpsConversationListView.as_view(), name="conversation-list"),
    path("conversations/<uuid:conversation_id>/", views.OpsConversationDetailView.as_view(), name="conversation-detail"),
    path("conversations/<uuid:conversation_id>/claim/", views.ConversationClaimView.as_view(), name="conversation-claim"),
    path("conversations/<uuid:conversation_id>/assign/", views.ConversationAssignView.as_view(), name="conversation-assign"),
    path("conversations/<uuid:conversation_id>/transfer/", views.ConversationTransferView.as_view(), name="conversation-transfer"),
    path("conversations/<uuid:conversation_id>/resolve/", views.ConversationResolveView.as_view(), name="conversation-resolve"),
    path("conversations/<uuid:conversation_id>/close/", views.ConversationCloseView.as_view(), name="conversation-close"),
    path("conversations/<uuid:conversation_id>/tags/", views.ConversationTagView.as_view(), name="conversation-tags"),
    # Transcripts
    path("transcripts/<uuid:conversation_id>/", views.TranscriptView.as_view(), name="transcript"),
]
