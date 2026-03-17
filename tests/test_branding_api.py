"""Tests for the branding config admin API."""

import pytest

from apps.admin_config.models import BrandingConfig


@pytest.mark.django_db
class TestBrandingConfigListCreate:
    def test_list_empty(self, ops_client):
        response = ops_client.get("/api/v1/admin/branding/")
        assert response.status_code == 200
        assert response.data == []

    def test_create_deployment_default(self, ops_client):
        response = ops_client.post(
            "/api/v1/admin/branding/",
            data={
                "severity_colors": {"critical": "#FF0000"},
                "header_text": "Custom Header",
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["org_id"] is None
        assert response.data["severity_colors"] == {"critical": "#FF0000"}
        assert response.data["header_text"] == "Custom Header"
        assert BrandingConfig.objects.count() == 1

    def test_create_per_org(self, ops_client):
        response = ops_client.post(
            "/api/v1/admin/branding/",
            data={
                "org_id": "org-abc",
                "severity_colors": {"high": "#FFA500"},
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["org_id"] == "org-abc"

    def test_list_returns_all(self, ops_client):
        BrandingConfig.objects.create(org_id=None, severity_colors={"critical": "danger"})
        BrandingConfig.objects.create(org_id="org-abc", severity_colors={"high": "#FFA500"})

        response = ops_client.get("/api/v1/admin/branding/")
        assert response.status_code == 200
        assert len(response.data) == 2

    def test_duplicate_org_id_rejected(self, ops_client):
        BrandingConfig.objects.create(org_id="org-abc")

        response = ops_client.post(
            "/api/v1/admin/branding/",
            data={"org_id": "org-abc"},
            format="json",
        )

        # Should fail due to unique constraint
        assert response.status_code >= 400

    def test_unauthenticated_rejected(self, api_client):
        response = api_client.get("/api/v1/admin/branding/")
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestBrandingConfigDetail:
    def test_get_config(self, ops_client):
        config = BrandingConfig.objects.create(
            org_id="org-abc",
            severity_colors={"critical": "#FF0000"},
            header_text="Test Header",
        )

        response = ops_client.get(f"/api/v1/admin/branding/{config.id}/")
        assert response.status_code == 200
        assert response.data["org_id"] == "org-abc"
        assert response.data["header_text"] == "Test Header"

    def test_get_nonexistent_returns_404(self, ops_client):
        response = ops_client.get("/api/v1/admin/branding/9999/")
        assert response.status_code == 404

    def test_patch_config(self, ops_client):
        config = BrandingConfig.objects.create(
            org_id="org-abc",
            severity_colors={"critical": "#FF0000"},
            header_text="Old Header",
        )

        response = ops_client.patch(
            f"/api/v1/admin/branding/{config.id}/",
            data={"header_text": "New Header"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["header_text"] == "New Header"
        # severity_colors unchanged
        assert response.data["severity_colors"] == {"critical": "#FF0000"}

    def test_delete_config(self, ops_client):
        config = BrandingConfig.objects.create(org_id="org-abc")

        response = ops_client.delete(f"/api/v1/admin/branding/{config.id}/")
        assert response.status_code == 204
        assert BrandingConfig.objects.count() == 0

    def test_delete_nonexistent_returns_404(self, ops_client):
        response = ops_client.delete("/api/v1/admin/branding/9999/")
        assert response.status_code == 404
