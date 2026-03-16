from django.contrib import admin

from .models import Assignment, Conversation, ConversationTag, Tag


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = [
        "id", "customer_name", "customer_org_name", "status", "queue",
        "assigned_analyst", "severity", "opened_at",
    ]
    list_filter = ["status", "queue", "severity", "source_channel"]
    search_fields = ["customer_name", "customer_email", "customer_org_name", "id"]
    readonly_fields = ["id", "roam_thread_key", "created_at", "updated_at"]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ["conversation", "analyst", "assigned_by", "assigned_at", "ended_at"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["key", "label"]


@admin.register(ConversationTag)
class ConversationTagAdmin(admin.ModelAdmin):
    list_display = ["conversation", "tag", "applied_by", "applied_at"]
