"""Analytics URL configuration."""

from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("dashboard/", views.DashboardKPIView.as_view(), name="dashboard"),
    path("hourly-volume/", views.HourlyVolumeView.as_view(), name="hourly-volume"),
    path("analyst-handled/", views.AnalystLeaderboardView.as_view(), name="analyst-handled"),
]
