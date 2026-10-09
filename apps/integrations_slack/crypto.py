"""Encryption for stored Slack bot tokens."""

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet() -> Fernet:
    key = getattr(settings, "SLACK_TOKEN_ENCRYPTION_KEY", "")
    if not key:
        raise ImproperlyConfigured("SLACK_TOKEN_ENCRYPTION_KEY is not set")
    return Fernet(key.encode())


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode()).decode()
