"""AI backend status and auth endpoints."""
import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .envelope import error_response, start_timing, success_response


@require_GET
def ai_status(request):
    """GET /api/ai/status — check AI backend and auth status."""
    start_timing()
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
        return JsonResponse(success_response({
            "backend": "cli",
            "ready": auth["logged_in"],
            "detail": detail,
            "setup_hint": "POST /api/ai/auth/start/ to begin login" if not auth["logged_in"] else None,
        }))
    else:
        has_key = bool(getattr(settings, "ANTHROPIC_API_KEY", ""))
        return JsonResponse(success_response({
            "backend": "api",
            "ready": has_key,
            "detail": "API key configured" if has_key else "No ANTHROPIC_API_KEY set",
        }))


# ── Auth flow endpoints (for CLI backend in Docker) ─────────────────


@csrf_exempt
@require_http_methods(["POST"])
def auth_start(request):
    """POST /api/ai/auth/start/ — begin setup-token flow, return auth URL."""
    start_timing()
    from . import auth_flow

    try:
        result = auth_flow.start()
        return JsonResponse(success_response(result))
    except FileNotFoundError:
        return JsonResponse(
            error_response("cli_not_found", "Claude CLI not installed"),
            status=500,
        )
    except RuntimeError as e:
        return JsonResponse(error_response("auth_start_failed", str(e)), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def auth_complete(request):
    """POST /api/ai/auth/complete/ — send pasted code, get back OAuth token."""
    start_timing()
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
        return JsonResponse(success_response({
            "token_preview": visible,
            "status": "authenticated",
        }))
    except RuntimeError as e:
        return JsonResponse(error_response("auth_complete_failed", str(e)), status=400)


@require_GET
def auth_poll(request):
    """GET /api/ai/auth/poll/ — check if setup-token completed without code paste."""
    start_timing()
    from . import auth_flow

    return JsonResponse(success_response(auth_flow.poll()))
