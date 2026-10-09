"""Slack-facing endpoints: OAuth install/callback and the Events API."""

import json
import logging
from html import escape
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.actions.views import _html_page
from apps.organizations.models import Organization

from . import oauth
from .client import SlackApiError
from .services import InstallConflictError, notify_installer, record_installation
from .tasks import process_slack_event, process_slack_interaction
from .verification import verify_slack_signature

logger = logging.getLogger(__name__)


@require_GET
def install(request):
    """Direct install link for installs that start from Slack. The workspace is linked to an org afterwards."""
    return HttpResponseRedirect(oauth.build_authorize_url())


@require_GET
def oauth_callback(request):
    if request.GET.get("error"):
        return _html_page("Install cancelled", "<h1>Install cancelled</h1><p>The Cyflare app was not installed.</p>")

    state = oauth.consume_state(request.GET.get("state", ""))
    code = request.GET.get("code", "")
    if not state or not code:
        return _html_page(
            "Link expired",
            "<h1 class='error'>This install link has expired</h1><p>Please start the install again.</p>",
            status_code=400,
        )

    try:
        oauth_data = oauth.exchange_code(code)
        install_, claim_code = record_installation(oauth_data, org_id=state.get("org"), user_id=state.get("uid"))
    except InstallConflictError:
        return _html_page(
            "Already connected",
            "<h1 class='error'>Workspace already connected</h1>"
            "<p>This Slack workspace is already connected to a different Cyflare organization. "
            "Contact Cyflare support if this is unexpected.</p>",
            status_code=409,
        )
    except SlackApiError:
        logger.exception("Slack OAuth code exchange failed")
        return _html_page(
            "Install failed",
            "<h1 class='error'>Install failed</h1><p>Slack did not complete the install. Please try again.</p>",
            status_code=502,
        )

    team = escape(install_.team_name or install_.team_id)
    if claim_code:
        claim_url = getattr(settings, "SLACK_CLAIM_URL", "")
        if claim_url:
            return HttpResponseRedirect(f"{claim_url}?{urlencode({'code': claim_code})}")
        notify_installer(
            install_,
            "Thanks for installing Cyflare. To finish setup, a Cyflare ONE user in your organization "
            f"needs to link this workspace using code `{claim_code}`.",
        )
        return _html_page(
            "Almost done",
            f"<h1>Almost done</h1><p>The Cyflare app is installed in <strong>{team}</strong>, "
            "but it isn't linked to your Cyflare organization yet.</p>"
            f"<p>In Cyflare ONE, link this workspace with code:</p><p><code>{escape(claim_code)}</code></p>",
        )

    org = Organization.objects.filter(org_id=install_.org_id).first()
    org_label = escape(org.name if org and org.name else install_.org_id)
    notify_installer(
        install_,
        f"Cyflare is now connected to this workspace for *{org_label}*. "
        "Invite me to a channel (`/invite @Cyflare`) or message me here to reach the Cyflare SOC. "
        "If you didn't expect this, uninstall the app from your Slack settings.",
    )
    return _html_page(
        "Connected",
        f"<h1>Slack connected</h1><p><strong>{team}</strong> is now connected to "
        f"<strong>{org_label}</strong>.</p><p>You can close this tab.</p>",
    )


@csrf_exempt
@require_POST
def events(request):
    if not verify_slack_signature(
        body=request.body,
        timestamp=request.headers.get("X-Slack-Request-Timestamp", ""),
        signature=request.headers.get("X-Slack-Signature", ""),
    ):
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)

    if payload.get("type") == "url_verification":
        return JsonResponse({"challenge": payload.get("challenge", "")})

    if payload.get("type") == "event_callback":
        # Slack requires an ack within 3 seconds, so the work happens in Celery.
        try:
            process_slack_event.delay(payload)
        except Exception:
            logger.exception("Failed to enqueue Slack event %s", payload.get("event_id"))
            return HttpResponse(status=500)  # Slack will retry

    return HttpResponse(status=200)


@csrf_exempt
@require_POST
def interactivity(request):
    """Button clicks. Slack sends a form-encoded ``payload`` field and expects an ack within 3 seconds."""
    if not verify_slack_signature(
        body=request.body,
        timestamp=request.headers.get("X-Slack-Request-Timestamp", ""),
        signature=request.headers.get("X-Slack-Signature", ""),
    ):
        return HttpResponse(status=401)
    try:
        payload = json.loads(request.POST.get("payload", ""))
    except ValueError:
        return HttpResponse(status=400)
    try:
        process_slack_interaction.delay(payload)
    except Exception:
        logger.exception("Failed to enqueue Slack interaction")
        return HttpResponse(status=500)
    return HttpResponse(status=200)
