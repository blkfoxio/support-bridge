"""Smoke tests to verify the scaffold boots correctly."""

import json

from django.test import RequestFactory

from config.urls import health_check, version_info


class TestHealthAndVersion:
    def test_health_check_returns_ok(self):
        factory = RequestFactory()
        request = factory.get("/health/")
        response = health_check(request)
        assert response.status_code == 200
        assert json.loads(response.content) == {"status": "ok"}

    def test_version_returns_version(self):
        factory = RequestFactory()
        request = factory.get("/version/")
        response = version_info(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "version" in data

    def test_api_docs_url_resolves(self):
        from django.urls import reverse

        url = reverse("swagger-ui")
        assert url == "/api/docs/"

    def test_api_schema_url_resolves(self):
        from django.urls import reverse

        url = reverse("schema")
        assert url == "/api/schema/"
