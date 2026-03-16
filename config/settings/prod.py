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
