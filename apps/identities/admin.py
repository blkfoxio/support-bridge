from django.contrib import admin

from .models import ExternalIdentity


@admin.register(ExternalIdentity)
class ExternalIdentityAdmin(admin.ModelAdmin):
    list_display = ["display_name", "email", "provider", "team_id", "org_id", "linked_user_id", "created_at"]
    list_filter = ["provider"]
    search_fields = ["display_name", "email", "external_user_id", "linked_user_id", "org_id"]
