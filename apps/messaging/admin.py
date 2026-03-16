from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "actor_type", "direction", "source", "message_type", "created_at"]
    list_filter = ["actor_type", "direction", "source", "message_type"]
    search_fields = ["body_plain", "actor_id"]
    readonly_fields = ["id", "created_at"]
