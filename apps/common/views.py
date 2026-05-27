"""AI backend status and auth endpoints."""
import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods


@require_GET
def ai_status(request):
    """GET /api/ai/status — check AI backend and auth status."""
    backend = getattr(settings, "AI_BACKEND", "api")

    if backend == "cli":
        from .anthropic_client import cli_auth_status

        auth = cli_auth_status()
        if auth["logged_in"]:
            detail = "Authenticated via Claude subscription"
        elif not auth["installed"]:
            detail = "Claude CLI not installed"
        else:
            detail = "Sign in to connect your Claude subscription"
        return JsonResponse({
            "backend": "cli",
            "ready": auth["logged_in"],
            "detail": detail,
            "setup_hint": "POST /api/ai/auth/start/ to begin login" if not auth["logged_in"] else None,
        })
    else:
        has_key = bool(getattr(settings, "ANTHROPIC_API_KEY", ""))
        return JsonResponse({
            "backend": "api",
            "ready": has_key,
            "detail": "API key configured" if has_key else "No ANTHROPIC_API_KEY set",
        })


@require_http_methods(["POST"])
def ai_switch(request):
    """POST /api/ai/switch/ — switch AI backend between 'api' and 'cli'."""
    try:
        body = json.loads(request.body)
        backend = body.get("backend", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"detail": "Expected JSON with 'backend' field"}, status=400)

    if backend not in ("api", "cli"):
        return JsonResponse({"detail": "backend must be 'api' or 'cli'"}, status=400)

    # Switch at runtime by updating the Django setting
    settings.AI_BACKEND = backend

    # Reset the cached API client so it picks up any changes
    from . import anthropic_client
    anthropic_client._client = None
    anthropic_client._consecutive_failures = 0

    return JsonResponse({"backend": backend})


# ── Auth flow endpoints (for CLI backend in Docker) ─────────────────


@require_http_methods(["POST"])
def auth_start(request):
    """POST /api/ai/auth/start/ — begin setup-token flow, return auth URL."""
    from . import auth_flow

    try:
        result = auth_flow.start()
        return JsonResponse(result)
    except FileNotFoundError:
        return JsonResponse({"detail": "Claude CLI not installed"}, status=500)
    except RuntimeError as e:
        return JsonResponse({"detail": str(e)}, status=500)


@require_http_methods(["POST"])
def auth_complete(request):
    """POST /api/ai/auth/complete/ — send pasted code, get back OAuth token."""
    from . import auth_flow

    code = None
    if request.body:
        try:
            body = json.loads(request.body)
            code = body.get("code", "").strip()
        except (json.JSONDecodeError, AttributeError):
            pass

    try:
        token = auth_flow.complete(code or None)
        # Redact middle of token for the response
        visible = token[:12] + "..." + token[-4:]
        return JsonResponse({
            "token_preview": visible,
            "status": "authenticated",
        })
    except RuntimeError as e:
        return JsonResponse({"detail": str(e)}, status=400)


@require_GET
def auth_poll(request):
    """GET /api/ai/auth/poll/ — check if setup-token completed without code paste."""
    from . import auth_flow

    return JsonResponse(auth_flow.poll())
