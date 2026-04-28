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

# Read endpoints callable with a Bearer token. Exact-match paths only —
# scoped tightly to slim "what projects exist?" lookups so machine clients
# (like the canopy portfolio-guide skill) can iterate without a session
# cookie. Anything richer (full project list, contexts, guides) still
# requires OAuth.
WORKBENCH_TOKEN_READABLE_PATHS = ("/api/projects/slugs/",)


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in PUBLIC_PATH_PREFIXES)


def _is_token_writable_path(path: str) -> bool:
    if not path.startswith("/api/projects/"):
        return False
    return any(path.endswith(suffix) for suffix in WORKBENCH_TOKEN_WRITE_SUFFIXES)


def _is_token_readable_path(method: str, path: str) -> bool:
    return method == "GET" and path in WORKBENCH_TOKEN_READABLE_PATHS


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

        # Bearer-token bypass for a narrow set of machine endpoints.
        expected_token = getattr(settings, "WORKBENCH_WRITE_TOKEN", "")
        writable = _is_token_writable_path(request.path)
        readable = _is_token_readable_path(request.method, request.path)
        provided = _extract_bearer_token(request)
        if expected_token and (writable or readable):
            if provided and provided == expected_token:
                request._workbench_token_auth = True
                request._dont_enforce_csrf_checks = True
                return self.get_response(request)

        if request.path.startswith("/api/"):
            # Temporary diagnostic header (safe — only length + prefix, never the value)
            token_len = len(expected_token) if expected_token else 0
            provided_len = len(provided) if provided else 0
            resp = JsonResponse({"detail": "Authentication required"}, status=401)
            resp["X-Debug-Writable"] = str(writable)
            resp["X-Debug-Expected-Len"] = str(token_len)
            resp["X-Debug-Provided-Len"] = str(provided_len)
            resp["X-Debug-Match"] = str(bool(expected_token and provided and provided == expected_token))
            return resp

        return redirect(f"{settings.LOGIN_URL}?next={request.path}")
