"""Workspace scoping of the /api/walkthroughs collection LIST + a proof that
token-gated public (visibility=link) detail reads survive scoping.

The authenticated LIST is workspace-scoped (a member sees their workspace's
walkthroughs; an outsider does not). The single-object public detail GET resolves
by UUID and self-enforces visibility — it must keep serving `visibility=link`
walkthroughs to anonymous callers presenting the matching ?t=<share_token>, with
NO workspace filter.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from apps.walkthroughs.models import Walkthrough
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture(autouse=True)
def _domain(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = "dimagi.com"


def _user(email, **kw):
    return User.objects.create(username=email, email=email, **kw)


def _client(u):
    c = Client()
    c.force_login(u)
    return c


def _workspace(slug, owner, *, auto_join=("dimagi.com",)):
    ws = Workspace.objects.create(
        slug=slug,
        display_name=slug.title(),
        created_by=owner,
        auto_join_domains=list(auto_join),
    )
    WorkspaceMembership.objects.get_or_create(
        workspace=ws, user=owner, defaults={"role": WorkspaceMembership.OWNER}
    )
    return ws


def _make(owner, ws, **kw):
    defaults = dict(
        title="Demo",
        kind="video",
        owner=owner,
        workspace=ws,
        drive_file_id="file-1",
        drive_folder_id="folder-1",
        content_type="video/mp4",
        size_bytes=10,
    )
    defaults.update(kw)
    return Walkthrough.objects.create(**defaults)


def test_member_sees_own_workspace_walkthrough_in_list():
    jj = _user("jj@dimagi.com", is_superuser=True)
    ws = _workspace("dimagi", jj)
    w = _make(jj, ws, title="Mine")

    items = _client(jj).get("/api/walkthroughs/").json()
    assert any(item["id"] == str(w.id) for item in items)


def test_outsider_does_not_see_the_walkthrough():
    jj = _user("jj@dimagi.com", is_superuser=True)
    ws = _workspace("dimagi", jj)
    w = _make(jj, ws, title="Mine")

    # An outsider on a different domain never auto-joins `dimagi`.
    outsider = _user("x@other.com")
    items = _client(outsider).get("/api/walkthroughs/").json()
    assert all(item["id"] != str(w.id) for item in items)


def test_domain_teammate_auto_joins_and_sees_walkthrough():
    jj = _user("jj@dimagi.com", is_superuser=True)
    ws = _workspace("dimagi", jj)
    w = _make(jj, ws, title="Mine")

    teammate = _user("t@dimagi.com")  # never explicitly added
    items = _client(teammate).get("/api/walkthroughs/").json()
    assert any(item["id"] == str(w.id) for item in items)


@override_settings(REQUIRE_AUTH=True)
def test_anonymous_can_still_get_link_visibility_detail_after_scoping():
    """The critical invariant: a `visibility=link` walkthrough remains readable
    by ANYONE with the URL + matching ?t=<share_token> — the workspace filter
    must NOT touch the public single-object read path."""
    jj = _user("jj@dimagi.com", is_superuser=True)
    ws = _workspace("dimagi", jj)
    w = _make(jj, ws, visibility="link")
    token = w.ensure_share_token()

    resp = Client().get(f"/api/walkthroughs/{w.id}/?t={token}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(w.id)
