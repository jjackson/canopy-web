"""
Project-level views for canopy-web.
"""
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET


def health_check(request):
    """Simple health check endpoint."""
    return JsonResponse({"status": "ok"})


@require_GET
def me_view(request):
    """Return the current user, or 401 if unauthenticated."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"detail": "Authentication required"}, status=401)

    avatar_url = ""
    social = user.socialaccount_set.filter(provider="google").first() if hasattr(user, "socialaccount_set") else None
    if social:
        avatar_url = social.extra_data.get("picture", "") or ""

    return JsonResponse({
        "email": user.email,
        "name": (user.get_full_name() or user.username or user.email),
        "avatar_url": avatar_url,
    })


@require_GET
@ensure_csrf_cookie
def csrf_view(request):
    """Force the CSRF cookie to be set. The SPA hits this once at boot."""
    return JsonResponse({"ok": True})


def spa_view(request):
    """Serve the built SPA index.html for any non-API route.

    In production, WhiteNoise serves /static/ and /assets/ assets referenced
    by index.html. In development, Vite serves the SPA directly — this view
    is only hit when the frontend build output is present.
    """
    index_path: Path = settings.FRONTEND_DIST_DIR / "index.html"
    if not index_path.exists():
        return HttpResponse(
            "Frontend build not found. Run `cd frontend && npm run build` "
            "or use the Vite dev server.",
            status=503,
            content_type="text/plain",
        )
    return FileResponse(open(index_path, "rb"), content_type="text/html")
