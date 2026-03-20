"""Views for serving the embeddable Support Bridge chat widget."""

from pathlib import Path

from django.http import HttpResponse, Http404


# Path to the built widget bundle
WIDGET_DIR = Path(__file__).resolve().parent.parent.parent / "widget" / "dist"


def widget_js(request):
    """Serve the compiled widget.js bundle with appropriate headers."""
    js_path = WIDGET_DIR / "widget.js"

    if not js_path.exists():
        raise Http404("Widget bundle not found. Run 'npm run build' in the widget/ directory.")

    content = js_path.read_text(encoding="utf-8")

    response = HttpResponse(content, content_type="application/javascript; charset=utf-8")

    # Cache for 1 hour in browsers, 1 day at CDN/proxy
    response["Cache-Control"] = "public, max-age=3600, s-maxage=86400"

    # Allow embedding from any origin
    response["Access-Control-Allow-Origin"] = "*"

    return response
