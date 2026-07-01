"""Tests for current_workspace() / user_default_workspace() — the single
resolution point that lets headless PAT callers act in a workspace without
naming one, and rejects ambiguous/non-member cases."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.workspaces import services as wsvc
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db
User = get_user_model()


def _mk_user(email="a@dimagi.com"):
    return User.objects.create(username=email, email=email)


def _mk_ws(slug, owner):
    ws = Workspace.objects.create(slug=slug, display_name=slug.title(), created_by=owner)
    wsvc.ensure_member(ws, owner, WorkspaceMembership.OWNER)
    return ws


def test_sole_membership_is_default():
    u = _mk_user()
    ws = _mk_ws("dimagi", u)
    assert wsvc.user_default_workspace(u) == ws
    assert wsvc.current_workspace(u) == ws


def test_explicit_member_slug_resolves():
    u = _mk_user()
    _mk_ws("dimagi", u)
    other = _mk_ws("acme", u)
    assert wsvc.current_workspace(u, explicit="acme") == other


def test_explicit_non_member_raises():
    u = _mk_user()
    _mk_ws("dimagi", u)
    stranger = _mk_user("b@dimagi.com")
    _mk_ws("ghost", stranger)  # u is NOT a member
    with pytest.raises(ValueError):
        wsvc.current_workspace(u, explicit="ghost")


def test_ambiguous_without_explicit_raises():
    u = _mk_user()
    _mk_ws("dimagi", u)
    _mk_ws("acme", u)  # two memberships, no explicit
    assert wsvc.user_default_workspace(u) is None
    with pytest.raises(ValueError):
        wsvc.current_workspace(u)
