from .base import *  # noqa: F401, F403

DEBUG = False

# Use JSON logging in production
LOGGING["handlers"]["console"]["formatter"] = "json"  # noqa: F405

# Security
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

# CORS — mobile app needs cross-origin access
INSTALLED_APPS += ["corsheaders"]  # noqa: F405
MIDDLEWARE.insert(1, "corsheaders.middleware.CorsMiddleware")  # noqa: F405
CORS_ALLOW_ALL_ORIGINS = True  # Prototype: allow all. Restrict later.
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "idempotency-key",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]
