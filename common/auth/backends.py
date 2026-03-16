"""Authentication backends for the Support Bridge API."""

import logging

from django.conf import settings
from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)


class FirebaseUser:
    """Lightweight user object representing a Firebase-authenticated customer."""

    def __init__(self, uid: str, email: str | None = None, claims: dict | None = None):
        self.uid = uid
        self.email = email or ""
        self.claims = claims or {}
        self.is_authenticated = True

    @property
    def org_id(self) -> str | None:
        return self.claims.get("org_id")

    def __str__(self) -> str:
        return f"FirebaseUser({self.uid})"


class FirebaseJWTAuthentication(authentication.BaseAuthentication):
    """DRF authentication class that validates Firebase ID tokens."""

    keyword = "Bearer"

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        token = parts[1]

        try:
            import firebase_admin
            from firebase_admin import auth as firebase_auth

            # Initialize Firebase app if not already done
            try:
                firebase_admin.get_app()
            except ValueError:
                if settings.FIREBASE_SERVICE_ACCOUNT_KEY:
                    import json
                    import base64

                    try:
                        # Try base64-encoded JSON first
                        key_data = json.loads(base64.b64decode(settings.FIREBASE_SERVICE_ACCOUNT_KEY))
                        cred = firebase_admin.credentials.Certificate(key_data)
                    except Exception:
                        # Try as file path
                        cred = firebase_admin.credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_KEY)
                    firebase_admin.initialize_app(cred)
                else:
                    # Use default credentials (for local dev with emulator)
                    firebase_admin.initialize_app()

            decoded_token = firebase_auth.verify_id_token(token)
            user = FirebaseUser(
                uid=decoded_token["uid"],
                email=decoded_token.get("email"),
                claims=decoded_token,
            )
            return (user, token)

        except ImportError:
            logger.error("firebase-admin package is not installed")
            raise exceptions.AuthenticationFailed("Firebase authentication is not configured")
        except Exception as e:
            logger.warning("Firebase token validation failed: %s", str(e))
            raise exceptions.AuthenticationFailed("Invalid or expired Firebase token")


class ApiKeyAuthentication(authentication.BaseAuthentication):
    """Simple API key authentication for ops/admin endpoints."""

    keyword = "X-API-Key"

    def authenticate(self, request):
        api_key = request.META.get("HTTP_X_API_KEY", "")
        if not api_key:
            return None

        if api_key != settings.OPS_API_KEY:
            raise exceptions.AuthenticationFailed("Invalid API key")

        # Return a simple user object for API key auth
        user = ApiKeyUser()
        return (user, api_key)


class ApiKeyUser:
    """Lightweight user object representing an API key-authenticated internal user."""

    def __init__(self):
        self.is_authenticated = True
        self.uid = "api-key-user"
        self.email = ""

    def __str__(self) -> str:
        return "ApiKeyUser"
