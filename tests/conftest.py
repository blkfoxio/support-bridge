"""Root conftest for pytest."""

import pytest
from rest_framework.test import APIClient

from common.auth.backends import ApiKeyUser, CognitoUser, FirebaseUser


@pytest.fixture
def api_client():
    """Return an unauthenticated DRF API client."""
    return APIClient()


@pytest.fixture
def firebase_user():
    """Return a mock Firebase-authenticated user."""
    return FirebaseUser(
        uid="test-user-123",
        email="testuser@example.com",
        claims={"org_id": "42"},
    )


@pytest.fixture
def cognito_user():
    """Return a mock Cognito-authenticated user."""
    return CognitoUser(
        uid="cognito-test-user-456",
        email="testuser@example.com",
        claims={"org_id": "42", "sub": "cognito-test-user-456"},
    )


@pytest.fixture
def authenticated_client(api_client, firebase_user):
    """Return an API client authenticated as a Firebase user."""
    api_client.force_authenticate(user=firebase_user)
    return api_client


@pytest.fixture
def cognito_authenticated_client(api_client, cognito_user):
    """Return an API client authenticated as a Cognito user."""
    api_client.force_authenticate(user=cognito_user)
    return api_client


@pytest.fixture
def ops_client(api_client):
    """Return an API client authenticated with an API key."""
    api_client.force_authenticate(user=ApiKeyUser())
    return api_client
