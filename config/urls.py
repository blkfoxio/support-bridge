from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from django.conf import settings


def health_check(request):
    return JsonResponse({"status": "ok"})


def version_info(request):
    return JsonResponse({"version": settings.APP_VERSION})


urlpatterns = [
    # System
    path("health/", health_check, name="health-check"),
    path("version/", version_info, name="version-info"),

    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # API namespaces
    path("api/v1/customer/", include("apps.customer_api.urls", namespace="customer-api")),
    path("api/v1/ops/", include("apps.ops_api.urls", namespace="ops-api")),
    path("api/v1/ops/analytics/", include("apps.analytics.urls", namespace="analytics")),
    path("api/v1/admin/", include("apps.admin_config.urls", namespace="admin-config")),

    # Actions (browser-based, triggered from Roam buttons)
    path("actions/", include("apps.actions.urls", namespace="actions")),

    # Webhooks
    path("webhooks/roam/", include("apps.integrations_roam.urls", namespace="roam-webhooks")),

    # Django admin
    path("django-admin/", admin.site.urls),
]
