"""Authentication middleware: default-deny with an allowlist.

Authenticated callers (via session cookie OR Personal Access Token via
`apps.tokens.middleware.BearerTokenAuthMiddleware`) bypass this gate
automatically — `request.user.is_authenticated` becomes True for both.
"""
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect

PUBLIC_PATH_PREFIXES = (
    "/accounts/",            # allauth login/logout/callback
    "/admin/",               # Django admin has its own auth
    "/health/",              # health check for Cloud Run
    "/static/",              # static assets
    "/api/csrf/",            # bootstraps CSRF cookie before login
    "/api/openapi.json",      # openapi-typescript fetches the schema
    "/api/docs/",             # Scalar HTML
    "/api/redoc/",            # Redoc HTML
    "/api/mcp/",              # FastMCP server — auth via Bearer in the request
    "/auth/cli/authorize/",   # @login_required handles its own OAuth bounce + preserves ?cb/?state/?label
)


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in PUBLIC_PATH_PREFIXES)


def _is_walkthrough_content(path: str) -> bool:
    # /w/<uuid>/content — the view itself enforces token-or-session auth.
    # We let it through the middleware so the per-token public link can
    # be served without a session cookie.
    return path.startswith("/w/") and path.endswith("/content")


class LoginRequiredMiddleware:
    """Require authentication for every request except the allowlist.

    API routes (anything under /api/) get a 401 JSON response.
    Everything else is redirected to the login URL.

    Personal Access Tokens authenticate via
    `apps.tokens.middleware.BearerTokenAuthMiddleware`, which runs
    *before* this middleware in the chain. A valid PAT promotes
    `request.user` to a real authenticated user, so this gate admits
    the request through the standard `is_authenticated` branch — no
    special-case Bearer handling required here anymore.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "REQUIRE_AUTH", True):
            return self.get_response(request)

        if (
            request.user.is_authenticated
            or _is_public(request.path)
            or _is_walkthrough_content(request.path)
        ):
            return self.get_response(request)

        if request.path.startswith("/api/"):
            return JsonResponse({"detail": "Authentication required"}, status=401)

        return redirect(f"{settings.LOGIN_URL}?next={request.path}")
