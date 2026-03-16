from django.contrib import admin

from .models import EventLog


@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    list_display = ["event_type", "idempotency_key", "source", "conversation", "created_at"]
    list_filter = ["event_type", "source"]
    search_fields = ["idempotency_key"]
    readonly_fields = ["created_at"]
