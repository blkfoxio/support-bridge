from django.contrib import admin

from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["org_id", "name", "slack_allow_unlinked_users", "slack_merge_window_minutes", "created_at"]
    search_fields = ["org_id", "name"]
