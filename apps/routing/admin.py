from django.contrib import admin

from .models import RoutingRule


@admin.register(RoutingRule)
class RoutingRuleAdmin(admin.ModelAdmin):
    list_display = ["name", "target_queue", "priority", "active", "created_at"]
    list_filter = ["active"]
