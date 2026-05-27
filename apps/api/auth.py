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

    Accepts EITHER a session cookie OR a Personal Access Token (PAT).
    `apps.tokens.middleware.BearerTokenAuthMiddleware` resolves
    `Authorization: Bearer <raw>` into a real `request.user` upstream,
    so by the time this auth class runs the only check is
    `request.user.is_authenticated`.
    """

    def authenticate(self, request: HttpRequest, key: str | None) -> object | None:
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
