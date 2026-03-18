"""Authentication backends for the Support Bridge API."""

import logging
import time

import httpx
import jwt
from django.conf import settings
from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# User objects
# ---------------------------------------------------------------------------


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


class CognitoUser:
    """Lightweight user object representing a Cognito-authenticated customer."""

    def __init__(self, uid: str, email: str | None = None, claims: dict | None = None):
        self.uid = uid
        self.email = email or ""
        self.claims = claims or {}
        self.is_authenticated = True

    @property
    def org_id(self) -> str | None:
        return self.claims.get("org_id")

    def __str__(self) -> str:
        return f"CognitoUser({self.uid})"


class ApiKeyUser:
    """Lightweight user object representing an API key-authenticated internal user."""

    def __init__(self):
        self.is_authenticated = True
        self.uid = "api-key-user"
        self.email = ""

    def __str__(self) -> str:
        return "ApiKeyUser"


# ---------------------------------------------------------------------------
# Cognito JWKS cache
# ---------------------------------------------------------------------------

_cognito_jwks_cache: dict | None = None
_cognito_jwks_fetched_at: float = 0
_JWKS_CACHE_TTL = 3600  # 1 hour


def _get_cognito_jwks() -> dict:
    """Fetch and cache the Cognito JWKS (JSON Web Key Set)."""
    global _cognito_jwks_cache, _cognito_jwks_fetched_at

    now = time.monotonic()
    if _cognito_jwks_cache and (now - _cognito_jwks_fetched_at) < _JWKS_CACHE_TTL:
        return _cognito_jwks_cache

    region = getattr(settings, "COGNITO_REGION", "us-east-1")
    user_pool_id = getattr(settings, "COGNITO_USER_POOL_ID", "")
    if not user_pool_id:
        raise exceptions.AuthenticationFailed("Cognito is not configured (missing COGNITO_USER_POOL_ID)")

    jwks_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
    try:
        resp = httpx.get(jwks_url, timeout=5)
        resp.raise_for_status()
        _cognito_jwks_cache = resp.json()
        _cognito_jwks_fetched_at = now
        return _cognito_jwks_cache
    except Exception as e:
        logger.error("Failed to fetch Cognito JWKS from %s: %s", jwks_url, e)
        # Return stale cache if available
        if _cognito_jwks_cache:
            return _cognito_jwks_cache
        raise exceptions.AuthenticationFailed("Unable to verify token: Cognito JWKS unavailable")


def _decode_cognito_token(token: str) -> dict:
    """Decode and validate a Cognito JWT access token."""
    region = getattr(settings, "COGNITO_REGION", "us-east-1")
    user_pool_id = getattr(settings, "COGNITO_USER_POOL_ID", "")
    issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"

    jwks = _get_cognito_jwks()

    # Extract the key ID from the token header to find the matching public key
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.DecodeError as e:
        raise exceptions.AuthenticationFailed(f"Invalid token header: {e}")

    kid = unverified_header.get("kid")
    if not kid:
        raise exceptions.AuthenticationFailed("Token missing key ID (kid)")

    # Find the matching key in the JWKS
    matching_key = None
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            matching_key = key_data
            break

    if not matching_key:
        # Key not found — try refreshing JWKS in case keys were rotated
        global _cognito_jwks_cache, _cognito_jwks_fetched_at
        _cognito_jwks_fetched_at = 0
        jwks = _get_cognito_jwks()
        for key_data in jwks.get("keys", []):
            if key_data.get("kid") == kid:
                matching_key = key_data
                break

    if not matching_key:
        raise exceptions.AuthenticationFailed("Token signed with unknown key")

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(matching_key)

    decoded = jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        issuer=issuer,
        options={"verify_aud": False},  # Cognito access tokens don't always have aud
    )
    return decoded


# ---------------------------------------------------------------------------
# Authentication classes
# ---------------------------------------------------------------------------


class CognitoJWTAuthentication(authentication.BaseAuthentication):
    """DRF authentication class that validates Cognito JWT access tokens."""

    keyword = "Bearer"

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        token = parts[1]

        # Quick heuristic: Cognito tokens are standard JWTs with 3 dot-separated parts.
        # Firebase ID tokens are also JWTs but issued by different issuers.
        # We try Cognito first; if the issuer doesn't match, return None so
        # the next auth class (Firebase) can try.
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            region = getattr(settings, "COGNITO_REGION", "us-east-1")
            user_pool_id = getattr(settings, "COGNITO_USER_POOL_ID", "")
            expected_issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
            token_issuer = unverified.get("iss")
            if token_issuer != expected_issuer:
                logger.warning(
                    "Cognito issuer mismatch: token_iss=%r expected=%r "
                    "(region=%r, pool_id=%r)",
                    token_issuer, expected_issuer, region, user_pool_id,
                )
                return None  # Not a Cognito token — let next auth class handle it
            logger.info("Cognito issuer matched: %s", expected_issuer)
        except Exception as e:
            logger.warning("Failed to decode token for issuer check: %s", e)
            return None  # Can't decode — not our token

        try:
            decoded = _decode_cognito_token(token)
            # Cognito access tokens use 'sub' as user ID and 'username' for email
            user = CognitoUser(
                uid=decoded.get("sub", ""),
                email=decoded.get("email") or decoded.get("username", ""),
                claims=decoded,
            )
            return (user, token)
        except exceptions.AuthenticationFailed:
            raise
        except Exception as e:
            logger.warning("Cognito token validation failed: %s", str(e))
            raise exceptions.AuthenticationFailed("Invalid or expired Cognito token")


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
                    import base64
                    import json

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
