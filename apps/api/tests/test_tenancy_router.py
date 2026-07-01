"""Tenant routing: the /api/w/{ws}/ prefix membership gate + the flat-route
compat shim (apps.api.tenancy.WorkspaceResolveMiddleware)."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.workspaces import services as wsvc
from apps.workspaces.models import Workspace, WorkspaceMembership

User = get_user_model()
pytestmark = pytest.mark.django_db


def _member(client, email="m@dimagi.com", slug="dimagi"):
    u = User.objects.create(username=email, email=email)
    ws = Workspace.objects.create(slug=slug, display_name=slug.title(), created_by=u)
    wsvc.ensure_member(ws, u, WorkspaceMembership.OWNER)
    client.force_login(u)
    return u, ws


def test_member_reaches_scoped_agents_list(client):
    _member(client)
    r = client.get("/api/w/dimagi/agents/")
    assert r.status_code == 200


def test_non_member_gets_404(client):
    _member(client)  # logged in as dimagi member
    stranger = User.objects.create(username="s@x.com", email="s@x.com")
    Workspace.objects.create(slug="secret", display_name="Secret", created_by=stranger)
    r = client.get("/api/w/secret/agents/")
    assert r.status_code == 404
    assert r["content-type"].startswith("application/problem+json")


def test_flat_agents_route_still_works(client):
    """Legacy flat /api/agents/ is the unchanged native mount — existing PAT /
    plugin callers keep working (workspace_slug stays None → default logic)."""
    _member(client)
    r = client.get("/api/agents/")
    assert r.status_code == 200


def test_prefixed_strips_to_flat_and_pins_workspace(client):
    """A member's /api/w/{ws}/agents/ call reroutes to the flat handler with the
    tenant pinned — proven by an agent in another workspace 404ing under the wrong ws."""
    u, ws = _member(client)
    from apps.agents.models import Agent
    Agent.objects.create(slug="echo", name="Echo", workspace=ws)
    assert client.get("/api/w/dimagi/agents/echo/").status_code == 200
    # a second workspace the user also belongs to, but echo isn't in it → 404
    other = Workspace.objects.create(slug="acme", display_name="Acme", created_by=u)
    wsvc.ensure_member(other, u, WorkspaceMembership.OWNER)
    assert client.get("/api/w/acme/agents/echo/").status_code == 404
