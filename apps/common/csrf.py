"""Manual CSRF enforcement for Ninja routes that opt out of auth classes.

Django Ninja marks its views ``csrf_exempt`` for Django's middleware and only
re-runs the CSRF check inside cookie-based auth classes (``APIKeyCookie``).
A route declared with ``auth=None`` that still mutates state on behalf of a
session-cookie caller therefore gets NO CSRF check anywhere — it must re-run
Django's check itself via this helper.

PAT/bearer callers are skipped automatically: ``BearerTokenAuthMiddleware``
sets ``request._dont_enforce_csrf_checks``, which Django's middleware honors.
"""
from django.http import HttpRequest
from django.middleware.csrf import CsrfViewMiddleware


def _noop_view(request):  # pragma: no cover - never actually called
    return None


def csrf_rejected(request: HttpRequest) -> bool:
    """Run Django's CSRF check on ``request``; True if it would be rejected."""
    mw = CsrfViewMiddleware(get_response=_noop_view)
    return mw.process_view(request, _noop_view, (), {}) is not None
