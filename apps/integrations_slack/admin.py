from django.contrib import admin

from .models import SlackInstallation


@admin.register(SlackInstallation)
class SlackInstallationAdmin(admin.ModelAdmin):
    list_display = ["team_name", "team_id", "org_id", "status", "installed_at", "activated_at"]
    list_filter = ["status"]
    search_fields = ["team_name", "team_id", "org_id"]
    exclude = ["bot_token_encrypted", "claim_code_hash"]
    readonly_fields = ["installed_at", "activated_at", "deactivated_at", "updated_at"]
