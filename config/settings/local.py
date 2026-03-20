import os

from .base import *  # noqa: F401, F403

DEBUG = True

# CORS — allow local Angular dev server
INSTALLED_APPS += ["corsheaders"]  # noqa: F405
MIDDLEWARE.insert(1, "corsheaders.middleware.CorsMiddleware")  # noqa: F405
CORS_ALLOW_ALL_ORIGINS = True

# Use simple console logging in development
LOGGING["handlers"]["console"]["formatter"] = "simple"  # noqa: F405

# Allow browsable API in development
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Use SQLite for testing when PostgreSQL isn't available
if os.environ.get("USE_SQLITE", "").lower() in ("1", "true", "yes") or "pytest" in os.environ.get("_", ""):
    DATABASES = {  # noqa: F405
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
