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

# Write endpoints callable with a Bearer token (machine writes like the
# canopy post_tool_use hook). Path must start with /api/projects/ AND end
# with one of these suffixes.
WORKBENCH_TOKEN_WRITE_SUFFIXES = ("/actions/", "/context/")


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in PUBLIC_PATH_PREFIXES)


def _is_token_writable_path(path: str) -> bool:
    if not path.startswith("/api/projects/"):
        return False
    return any(path.endswith(suffix) for suffix in WORKBENCH_TOKEN_WRITE_SUFFIXES)


def _extract_bearer_token(request) -> str | None:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return None
    return header[len("Bearer "):].strip() or None


class LoginRequiredMiddleware:
    """Require authentication for every request except the allowlist.

    API routes (anything under /api/) get a 401 JSON response.
    Everything else is redirected to the login URL.

    Machine callers can bypass OAuth on specific write endpoints
    (action tracking, context posting) by presenting
    ``Authorization: Bearer <WORKBENCH_WRITE_TOKEN>``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "REQUIRE_AUTH", True):
            return self.get_response(request)

        if request.user.is_authenticated or _is_public(request.path):
            return self.get_response(request)

        # Bearer-token bypass for a narrow set of machine write endpoints.
        expected_token = getattr(settings, "WORKBENCH_WRITE_TOKEN", "")
        if expected_token and _is_token_writable_path(request.path):
            provided = _extract_bearer_token(request)
            if provided and provided == expected_token:
                request._workbench_token_auth = True
                return self.get_response(request)

        if request.path.startswith("/api/"):
            return JsonResponse({"detail": "Authentication required"}, status=401)

        return redirect(f"{settings.LOGIN_URL}?next={request.path}")
