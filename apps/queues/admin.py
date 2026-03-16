from django.contrib import admin

from .models import AnalystProfile, Queue, QueueGroupMapping, SlaPolicy


@admin.register(Queue)
class QueueAdmin(admin.ModelAdmin):
    list_display = ["key", "name", "active", "priority_order", "created_at"]
    list_filter = ["active"]
    search_fields = ["key", "name"]


@admin.register(QueueGroupMapping)
class QueueGroupMappingAdmin(admin.ModelAdmin):
    list_display = ["queue", "roam_group_id", "roam_group_name", "active"]
    list_filter = ["active"]


@admin.register(AnalystProfile)
class AnalystProfileAdmin(admin.ModelAdmin):
    list_display = ["display_name", "email", "external_user_id", "active", "default_queue"]
    list_filter = ["active"]
    search_fields = ["display_name", "email"]


@admin.register(SlaPolicy)
class SlaPolicyAdmin(admin.ModelAdmin):
    list_display = ["queue", "first_response_seconds", "resolution_seconds", "active"]
    list_filter = ["active"]
