from django.urls import path

from . import api_views

app_name = "customer_slack"

urlpatterns = [
    path("install-url/", api_views.SlackInstallUrlView.as_view(), name="install-url"),
    path("claim/", api_views.SlackClaimView.as_view(), name="claim"),
    path("installations/", api_views.SlackInstallationListView.as_view(), name="installations"),
]
