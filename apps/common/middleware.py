"""Authentication middleware: default-deny with an allowlist."""
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect


PUBLIC_PATH_PREFIXES = (
    "/accounts/",        # allauth login/logout/callback
    "/admin/",           # Django admin has its own auth
    "/health/",          # health check for Cloud Run
    "/static/",          # static assets
    "/api/csrf/",        # bootstraps CSRF cookie before login
)


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in PUBLIC_PATH_PREFIXES)


class LoginRequiredMiddleware:
    """Require authentication for every request except the allowlist.

    API routes (anything under /api/) get a 401 JSON response.
    Everything else is redirected to the login URL.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "REQUIRE_AUTH", True):
            return self.get_response(request)

        if request.user.is_authenticated or _is_public(request.path):
            return self.get_response(request)

        if request.path.startswith("/api/"):
            return JsonResponse({"detail": "Authentication required"}, status=401)

        return redirect(f"{settings.LOGIN_URL}?next={request.path}")
