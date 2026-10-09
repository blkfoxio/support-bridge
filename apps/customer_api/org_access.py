"""Resolve and authorize the organization a customer request acts on."""

import logging

from rest_framework import status
from rest_framework.response import Response

from common.auth import one_org

logger = logging.getLogger(__name__)


def _error(code: str, message: str, http_status: int) -> Response:
    return Response({"error": {"code": code, "message": message, "status": http_status}}, status=http_status)


def authorize_org(request, requested_org_id: str | None) -> tuple[str | None, Response | None]:
    """Return ``(org_id, None)`` if the authenticated user may act on the org, else ``(None, error_response)``.

    The token's org claim wins over the requested value. When Cyflare ONE verification is
    configured, membership is confirmed there and the check fails closed if ONE can't answer.
    """
    token_org_id = getattr(request.user, "org_id", None)
    if token_org_id and requested_org_id and requested_org_id != token_org_id:
        return None, _error(
            "org_mismatch", "org_id does not match the authenticated user's organization", status.HTTP_403_FORBIDDEN
        )
    org_id = token_org_id or requested_org_id
    if not org_id:
        return None, _error("missing_org_id", "org_id is required", status.HTTP_400_BAD_REQUEST)

    if one_org.org_verification_enabled():
        try:
            allowed = one_org.user_can_access_org(token=request.auth, uid=request.user.uid, org_id=org_id)
        except one_org.OrgVerificationUnavailableError:
            logger.exception("Cyflare ONE org verification unavailable for uid=%s", request.user.uid)
            return None, _error(
                "org_verification_unavailable",
                "Unable to verify organization right now, please try again",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if not allowed:
            return None, _error(
                "org_forbidden", "You do not have access to this organization", status.HTTP_403_FORBIDDEN
            )

    return org_id, None
