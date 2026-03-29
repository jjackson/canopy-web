"""AI backend status endpoint."""
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .envelope import start_timing, success_response


@require_GET
def ai_status(request):
    """GET /api/ai/status — check AI backend and auth status."""
    start_timing()
    backend = getattr(settings, "AI_BACKEND", "api")

    if backend == "cli":
        from .anthropic_client import cli_auth_status
        auth = cli_auth_status()
        return JsonResponse(success_response({
            "backend": "cli",
            "ready": auth["logged_in"],
            "detail": auth["output"] if not auth["logged_in"] else "Authenticated via subscription",
            "setup_command": "docker compose exec -it backend claude setup-token" if not auth["logged_in"] else None,
        }))
    else:
        has_key = bool(getattr(settings, "ANTHROPIC_API_KEY", ""))
        return JsonResponse(success_response({
            "backend": "api",
            "ready": has_key,
            "detail": "API key configured" if has_key else "No ANTHROPIC_API_KEY set",
            "setup_command": None,
        }))
