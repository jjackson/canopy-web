"""AI backend status and auth management endpoints."""
import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .envelope import start_timing, success_response, error_response


@require_GET
def ai_status(request):
    """GET /api/ai/status — check AI backend configuration and auth status."""
    start_timing()
    backend = getattr(settings, "AI_BACKEND", "api")

    if backend == "cli":
        from .anthropic_client import cli_auth_status
        auth = cli_auth_status()
        return JsonResponse(success_response({
            "backend": "cli",
            "description": "Claude Code CLI (subscription login)",
            "installed": auth["installed"],
            "logged_in": auth["logged_in"],
            "detail": auth["output"],
            "ready": auth["logged_in"],
        }))
    else:
        has_key = bool(getattr(settings, "ANTHROPIC_API_KEY", ""))
        return JsonResponse(success_response({
            "backend": "api",
            "description": "Direct Anthropic API (API key)",
            "logged_in": has_key,
            "ready": has_key,
            "detail": "API key configured" if has_key else "No ANTHROPIC_API_KEY set",
        }))


@csrf_exempt
@require_POST
def ai_login(request):
    """POST /api/ai/login — start Claude CLI login flow.
    Returns the OAuth URL. The process stays alive waiting for the code."""
    start_timing()
    backend = getattr(settings, "AI_BACKEND", "api")

    if backend != "cli":
        return JsonResponse(
            error_response("not_cli", "Login only applies to AI_BACKEND=cli mode."),
            status=400,
        )

    from .anthropic_client import cli_start_login
    result = cli_start_login()
    return JsonResponse(success_response(result))


@csrf_exempt
@require_POST
def ai_login_code(request):
    """POST /api/ai/login/code — submit the OAuth code to complete login.
    Body: {"code": "the-auth-code-from-oauth"}"""
    start_timing()
    backend = getattr(settings, "AI_BACKEND", "api")

    if backend != "cli":
        return JsonResponse(
            error_response("not_cli", "Login only applies to AI_BACKEND=cli mode."),
            status=400,
        )

    try:
        body = json.loads(request.body)
        code = body.get("code", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse(
            error_response("invalid_body", "Send JSON with {\"code\": \"your-auth-code\"}"),
            status=400,
        )

    if not code:
        return JsonResponse(
            error_response("missing_code", "No auth code provided."),
            status=400,
        )

    from .anthropic_client import cli_submit_login_code
    result = cli_submit_login_code(code)

    if result["success"]:
        return JsonResponse(success_response(result))
    else:
        return JsonResponse(success_response(result), status=200)  # Still 200 — let frontend handle
