"""Custom DRF exception handler for consistent error responses."""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Return consistent error response format."""
    response = exception_handler(exc, context)

    if response is not None:
        error_data = {
            "error": {
                "code": _get_error_code(response.status_code),
                "message": _get_error_message(response),
                "status": response.status_code,
            }
        }
        response.data = error_data
    else:
        logger.exception("Unhandled exception: %s", exc)
        response = Response(
            {
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred",
                    "status": 500,
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response


def _get_error_code(status_code: int) -> str:
    code_map = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        429: "rate_limited",
        500: "internal_error",
        501: "not_implemented",
    }
    return code_map.get(status_code, "error")


def _get_error_message(response) -> str:
    if isinstance(response.data, dict):
        detail = response.data.get("detail", "")
        if detail:
            return str(detail)
    if isinstance(response.data, list):
        return "; ".join(str(item) for item in response.data)
    return str(response.data)
