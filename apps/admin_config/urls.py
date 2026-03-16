from django.urls import path

from . import views

app_name = "admin_config"

urlpatterns = [
    path("routing-rules/", views.RoutingRuleListView.as_view(), name="routing-rule-list"),
    path("routing-rules/<int:rule_id>/", views.RoutingRuleDetailView.as_view(), name="routing-rule-detail"),
    path("queue-group-mappings/", views.QueueGroupMappingListView.as_view(), name="queue-group-mapping-list"),
    path("queue-group-mappings/<int:mapping_id>/", views.QueueGroupMappingDetailView.as_view(), name="queue-group-mapping-detail"),
    path("analysts/", views.AnalystListView.as_view(), name="analyst-list"),
    path("audit/events/", views.AuditEventListView.as_view(), name="audit-event-list"),
]
