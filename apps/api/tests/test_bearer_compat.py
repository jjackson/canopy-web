"""Smoke tests: Bearer-token bypass continues to work for Ninja routes.

LoginRequiredMiddleware admits machine callers presenting a Bearer
token on a narrow allowlist (projects/*/actions/, projects/*/context/,
projects/slugs/, insights/). It sets `_workbench_token_auth = True`
and `_dont_enforce_csrf_checks = True` before handing off; Ninja's
CSRF + session_auth must honor both.

These tests use the smoke route under /api/_auth_smoke/ — it's
NOT on the bypass allowlist, so we can't test the real flow here.
Real Bearer compatibility is covered by per-app contract tests in
Phase 2 (Task 2.3 — projects bearer-readable endpoints).

Instead we test the auth class directly: a request carrying
_workbench_token_auth=True bypasses the is_authenticated check.
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.api.auth import session_auth


def test_session_auth_accepts_anonymous_when_bearer_authed():
    rf = RequestFactory()
    request = rf.get("/api/_anything")
    request.user = AnonymousUser()
    request._workbench_token_auth = True
    # Should not raise; should return whatever request.user is.
    result = session_auth.authenticate(request, None)
    assert result is request.user


def test_session_auth_rejects_anonymous_without_bearer_marker():
    from apps.api.errors import ProblemError

    rf = RequestFactory()
    request = rf.get("/api/_anything")
    request.user = AnonymousUser()
    with pytest.raises(ProblemError) as exc_info:
        session_auth.authenticate(request, None)
    assert exc_info.value.status_code == 401
