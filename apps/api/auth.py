"""Session-cookie auth for Django Ninja routes.

Trusts `request.user` populated by Django's auth middleware
(django-allauth sits on top of this). Raises
`ProblemError(401, "Authentication required")` when no user
is attached. Matches the standard Django auth model — Ninja
sees `request.user` exactly as a DRF view does.

The upstream `LoginRequiredMiddleware` already short-circuits
anonymous /api/ requests with a 401 JSON response. This auth
class is defense-in-depth + lets the schema declare auth.
"""
from __future__ import annotations

from django.http import HttpRequest
from ninja.security import SessionAuth

from .errors import TYPE_AUTH, ProblemError


class DjangoSessionAuth(SessionAuth):
    """Session auth that raises problem+json instead of returning None.

    Special-case: requests pre-authorized by the Bearer-token bypass
    in `apps/common/middleware.py` (writes to /api/projects/*/actions/
    + /api/projects/*/context/, reads of /api/projects/slugs/ +
    /api/insights/) carry `_workbench_token_auth = True`. We accept
    those even without an authenticated user.
    """

    def authenticate(self, request: HttpRequest, key: str | None) -> object | None:
        if getattr(request, "_workbench_token_auth", False):
            return getattr(request, "user", None)  # may be AnonymousUser — that's fine
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise ProblemError(
                401,
                "Authentication required",
                type_=TYPE_AUTH,
                detail="This endpoint requires an authenticated session.",
            )
        return user


session_auth = DjangoSessionAuth()
