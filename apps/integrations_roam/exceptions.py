"""Custom exception hierarchy for Roam API client."""


class RoamApiError(Exception):
    """Base exception for all Roam API errors."""

    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)


class RoamAuthError(RoamApiError):
    """Raised on 401/403 responses — invalid or expired token."""
    pass


class RoamRateLimitError(RoamApiError):
    """Raised on 429 responses — rate limit exceeded."""
    pass


class RoamNotFoundError(RoamApiError):
    """Raised on 404 responses — resource not found."""
    pass


class RoamServerError(RoamApiError):
    """Raised on 5xx responses — Roam server error."""
    pass
