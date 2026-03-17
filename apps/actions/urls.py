from django.urls import path

from . import views

app_name = "actions"

urlpatterns = [
    path(
        "resolve/<uuid:conversation_id>/",
        views.ResolveActionView.as_view(),
        name="resolve",
    ),
]
