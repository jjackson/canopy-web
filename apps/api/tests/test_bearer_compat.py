"""Smoke tests: DjangoSessionAuth post-PAT-refactor.

The previous `_workbench_token_auth` shortcut was retired when
`apps.tokens.middleware.BearerTokenAuthMiddleware` started resolving
`Authorization: Bearer <raw>` into a real `request.user` upstream.
DjangoSessionAuth no longer has a Bearer branch — it just checks
`request.user.is_authenticated`. These tests pin that contract.

Real end-to-end PAT-via-Bearer coverage lives in
`apps/tokens/tests/test_middleware.py` and the per-app
`tests/test_api.py::test_*_pat_*` cases.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.api.auth import session_auth
from apps.api.errors import ProblemError

User = get_user_model()


@pytest.mark.django_db
def test_session_auth_accepts_authenticated_user():
    user = User.objects.create_user(username="alice", email="alice@dimagi.com")
    rf = RequestFactory()
    request = rf.get("/api/_anything")
    request.user = user
    result = session_auth.authenticate(request, None)
    assert result.pk == user.pk


def test_session_auth_rejects_anonymous():
    rf = RequestFactory()
    request = rf.get("/api/_anything")
    request.user = AnonymousUser()
    with pytest.raises(ProblemError) as exc_info:
        session_auth.authenticate(request, None)
    assert exc_info.value.status_code == 401


def test_session_auth_rejects_request_without_user_attribute():
    rf = RequestFactory()
    request = rf.get("/api/_anything")
    # No request.user — pre-AuthenticationMiddleware state.
    with pytest.raises(ProblemError) as exc_info:
        session_auth.authenticate(request, None)
    assert exc_info.value.status_code == 401
