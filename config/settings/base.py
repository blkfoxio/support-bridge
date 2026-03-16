import os
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY", default="insecure-dev-key-change-me")

DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# Application definition

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.conversations",
    "apps.messaging",
    "apps.routing",
    "apps.queues",
    "apps.analytics",
    "apps.integrations_roam",
    "apps.customer_api",
    "apps.ops_api",
    "apps.admin_config",
    "apps.audit",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
DATABASE_URL = config("DATABASE_URL", default="postgres://support_bridge:support_bridge@localhost:5432/support_bridge")

# Parse DATABASE_URL
_db_parts = DATABASE_URL.replace("postgresql://", "").replace("postgres://", "").split("@")
_db_credentials = _db_parts[0].split(":")
_db_host_port_name = _db_parts[1].split("/")
_db_host_port = _db_host_port_name[0].split(":")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db_host_port_name[1] if len(_db_host_port_name) > 1 else "support_bridge",
        "USER": _db_credentials[0],
        "PASSWORD": _db_credentials[1] if len(_db_credentials) > 1 else "",
        "HOST": _db_host_port[0],
        "PORT": _db_host_port[1] if len(_db_host_port) > 1 else "5432",
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "common.auth.backends.FirebaseJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "common.utils.exception_handler.custom_exception_handler",
}

# drf-spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "Cyflare Support Bridge API",
    "DESCRIPTION": "API-first support orchestration service",
    "VERSION": config("APP_VERSION", default="0.1.0"),
    "SERVE_INCLUDE_SCHEMA": False,
    "TAGS": [
        {"name": "Customer - Conversations", "description": "Mobile-facing conversation endpoints"},
        {"name": "Ops - Queues", "description": "Queue management and metrics"},
        {"name": "Ops - Conversations", "description": "Operational conversation management"},
        {"name": "Admin - Config", "description": "Routing rules and queue-group mappings"},
        {"name": "Admin - Audit", "description": "Audit event retrieval"},
        {"name": "Webhooks", "description": "Roam webhook ingestion"},
        {"name": "System", "description": "Health and version endpoints"},
    ],
    "COMPONENT_SPLIT_REQUEST": True,
}

# Redis
REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

# Celery
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "poll-roam-replies": {
        "task": "roam.poll_replies",
        "schedule": 10.0,  # Every 10 seconds
    },
}

# Firebase
FIREBASE_SERVICE_ACCOUNT_KEY = config("FIREBASE_SERVICE_ACCOUNT_KEY", default="")

# Roam API
ROAM_API_BASE_URL = config("ROAM_API_BASE_URL", default="https://api.ro.am/v0")
ROAM_API_TOKEN = config("ROAM_API_TOKEN", default="")
ROAM_WEBHOOK_SECRET = config("ROAM_WEBHOOK_SECRET", default="")
ROAM_BOT_USER_ID = config("ROAM_BOT_USER_ID", default="")

# Ops/Admin API Key
OPS_API_KEY = config("OPS_API_KEY", default="change-me-in-production")

# App version
APP_VERSION = config("APP_VERSION", default="0.1.0")

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
        "simple": {
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
