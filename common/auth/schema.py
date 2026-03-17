"""drf-spectacular OpenAPI extensions for custom auth backends."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CognitoJWTAuthExtension(OpenApiAuthenticationExtension):
    target_class = "common.auth.backends.CognitoJWTAuthentication"
    name = "CognitoJWT"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Cognito Access Token",
            "description": "Cognito JWT access token from Cyflare ONE authentication",
        }


class FirebaseJWTAuthExtension(OpenApiAuthenticationExtension):
    target_class = "common.auth.backends.FirebaseJWTAuthentication"
    name = "FirebaseJWT"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Firebase ID Token",
            "description": "Firebase JWT token obtained via Firebase Auth SDK (legacy)",
        }


class ApiKeyAuthExtension(OpenApiAuthenticationExtension):
    target_class = "common.auth.backends.ApiKeyAuthentication"
    name = "ApiKey"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key for internal ops/admin endpoints",
        }
