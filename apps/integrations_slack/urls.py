from django.urls import path

from . import views

app_name = "integrations_slack"

urlpatterns = [
    path("install", views.install, name="install"),
    path("oauth/callback", views.oauth_callback, name="oauth-callback"),
    path("events", views.events, name="events"),
    path("interactivity", views.interactivity, name="interactivity"),
]
