"""Browser-based action views for Roam button URLs.

These views render simple HTML pages that execute actions when an analyst
clicks a button in Roam. The URL contains a signed token to prevent forgery.

Flow:
  1. Analyst clicks "Resolve" button in Roam message
  2. Browser opens this page with signed token
  3. GET shows a confirmation page with conversation details
  4. POST executes the action (resolve, etc.)
"""

import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.conversations.models import Conversation, ConversationStatus
from apps.conversations.services import ConversationService
from apps.integrations_roam.client import RoamClient
from apps.integrations_roam.mock_client import MockRoamClient
from django.conf import settings

from .tokens import verify_action_token

logger = logging.getLogger(__name__)


def _get_roam_client():
    if settings.ROAM_API_TOKEN:
        return RoamClient(settings.ROAM_API_BASE_URL, settings.ROAM_API_TOKEN)
    return MockRoamClient()


def _html_page(title: str, body: str, *, status_code: int = 200) -> HttpResponse:
    """Render a minimal branded HTML page."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — Cyflare Support Bridge</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #0f1117; color: #e2e8f0; min-height: 100vh;
           display: flex; align-items: center; justify-content: center; padding: 24px; }}
    .card {{ background: #1a1d28; border-radius: 12px; padding: 32px;
             max-width: 480px; width: 100%; box-shadow: 0 4px 24px rgba(0,0,0,0.3); }}
    h1 {{ font-size: 20px; margin-bottom: 8px; color: #f1f5f9; }}
    p {{ font-size: 14px; color: #94a3b8; line-height: 1.6; margin-bottom: 16px; }}
    .meta {{ font-size: 12px; color: #64748b; margin-bottom: 20px; }}
    .meta span {{ display: block; margin-bottom: 4px; }}
    .btn {{ display: inline-block; padding: 12px 24px; border-radius: 8px;
            font-size: 14px; font-weight: 600; cursor: pointer; border: none;
            text-decoration: none; text-align: center; }}
    .btn-resolve {{ background: #506C64; color: #fff; }}
    .btn-resolve:hover {{ background: #5f7e75; }}
    .btn-cancel {{ background: transparent; color: #94a3b8; margin-left: 12px; }}
    .success {{ color: #4ade80; }}
    .error {{ color: #f87171; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
              font-size: 11px; font-weight: 600; text-transform: uppercase; }}
    .badge-active {{ background: #166534; color: #4ade80; }}
    .badge-resolved {{ background: #1e3a5f; color: #60a5fa; }}
    .badge-closed {{ background: #374151; color: #9ca3af; }}
    form {{ display: inline; }}
  </style>
</head>
<body>
  <div class="card">{body}</div>
</body>
</html>"""
    return HttpResponse(html, content_type="text/html", status=status_code)


@method_decorator(csrf_exempt, name="dispatch")
class ResolveActionView(View):
    """Handle resolve action from Roam button click."""

    def get(self, request, conversation_id):
        token = request.GET.get("token", "")
        if not verify_action_token("resolve", str(conversation_id), token):
            return _html_page("Invalid Link", """
                <h1 class="error">Invalid or Expired Link</h1>
                <p>This action link is not valid. It may have been tampered with or is for a different conversation.</p>
            """, status_code=403)

        conversation = get_object_or_404(Conversation, pk=conversation_id)

        # Already resolved or closed
        if conversation.status == ConversationStatus.RESOLVED:
            return _html_page("Already Resolved", f"""
                <h1>Already Resolved</h1>
                <p>This conversation was already resolved.</p>
                <div class="meta">
                    <span><strong>Customer:</strong> {conversation.customer_name}</span>
                    <span><strong>Status:</strong> <span class="badge badge-resolved">Resolved</span></span>
                </div>
                <p>You can close this tab.</p>
            """)

        if conversation.status == ConversationStatus.CLOSED:
            return _html_page("Already Closed", f"""
                <h1>Already Closed</h1>
                <p>This conversation has already been closed.</p>
                <div class="meta">
                    <span><strong>Customer:</strong> {conversation.customer_name}</span>
                    <span><strong>Status:</strong> <span class="badge badge-closed">Closed</span></span>
                </div>
                <p>You can close this tab.</p>
            """)

        # Show confirmation
        return _html_page("Resolve Conversation", f"""
            <h1>Resolve Conversation</h1>
            <p>Mark this conversation as resolved? The customer will be asked to confirm or reopen.</p>
            <div class="meta">
                <span><strong>Customer:</strong> {conversation.customer_name} ({conversation.customer_email})</span>
                <span><strong>Organization:</strong> {conversation.customer_org_name}</span>
                <span><strong>Severity:</strong> {conversation.severity}</span>
                <span><strong>Status:</strong> <span class="badge badge-active">{conversation.status}</span></span>
            </div>
            <form method="post" action="?token={token}">
                <button type="submit" class="btn btn-resolve">Resolve Conversation</button>
            </form>
            <a href="javascript:window.close()" class="btn btn-cancel">Cancel</a>
        """)

    def post(self, request, conversation_id):
        token = request.GET.get("token", "")
        if not verify_action_token("resolve", str(conversation_id), token):
            return _html_page("Invalid Link", """
                <h1 class="error">Invalid or Expired Link</h1>
                <p>This action link is not valid.</p>
            """, status_code=403)

        conversation = get_object_or_404(Conversation, pk=conversation_id)

        # Idempotent — if already resolved, just show success
        if conversation.status in (ConversationStatus.RESOLVED, ConversationStatus.CLOSED):
            return _html_page("Already Resolved", f"""
                <h1 class="success">Already Resolved</h1>
                <p>This conversation was already in a terminal state.</p>
                <p>You can close this tab.</p>
            """)

        try:
            roam_client = _get_roam_client()
            service = ConversationService(roam_client)
            service.resolve_conversation(
                conversation_id=str(conversation_id),
                actor_id="roam_button",
            )
        except ValueError as e:
            return _html_page("Cannot Resolve", f"""
                <h1 class="error">Cannot Resolve</h1>
                <p>{e}</p>
            """, status_code=400)
        except Exception:
            logger.exception("Failed to resolve conversation %s via action button", conversation_id)
            return _html_page("Error", """
                <h1 class="error">Something went wrong</h1>
                <p>The conversation could not be resolved. Please try again or resolve manually.</p>
            """, status_code=500)

        return _html_page("Resolved", f"""
            <h1 class="success">Conversation Resolved</h1>
            <p>The customer has been notified and can confirm or reopen the conversation.</p>
            <div class="meta">
                <span><strong>Customer:</strong> {conversation.customer_name}</span>
                <span><strong>Conversation:</strong> {conversation_id}</span>
            </div>
            <p>You can close this tab.</p>
        """)
