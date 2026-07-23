"""SP2a Task 5 — the /api/canopy-sessions surface: create, get, send (stub inline), tenancy."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.agents.models import Agent
from apps.canopy_sessions.models import Session
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture()
def ctx():
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=user)
    WorkspaceMembership.objects.create(user=user, workspace=ws, role=WorkspaceMembership.OWNER)
    agent = Agent.objects.create(slug="echo", name="Echo", workspace=ws, owner=user)
    return user, ws, agent


@pytest.fixture()
def client(ctx):
    c = Client()
    c.force_login(ctx[0])
    return c


def test_create_and_get_empty_session(client):
    r = client.post("/api/canopy-sessions/", data={"agent_slug": "echo", "title": "T"}, content_type="application/json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["agent_slug"] == "echo"
    sid = body["id"]

    detail = client.get(f"/api/canopy-sessions/{sid}")
    assert detail.status_code == 200
    assert detail.json()["messages"] == []


def test_send_runs_stub_and_transcript_appears(client):
    sid = client.post("/api/canopy-sessions/", data={"agent_slug": "echo"}, content_type="application/json").json()["id"]
    r = client.post(f"/api/canopy-sessions/{sid}/send", data={"text": "hi"}, content_type="application/json")
    assert r.status_code == 200, r.content
    assert r.json()["message"]["role"] == "user"

    detail = client.get(f"/api/canopy-sessions/{sid}").json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]  # the stub executed and projected


def test_empty_text_rejected(client):
    sid = client.post("/api/canopy-sessions/", data={}, content_type="application/json").json()["id"]
    r = client.post(f"/api/canopy-sessions/{sid}/send", data={"text": "   "}, content_type="application/json")
    assert r.status_code == 422


def test_non_member_gets_404(client):
    other = User.objects.create_user("no", "no@dimagi.com", "pw")
    ws2 = Workspace.objects.create(slug="other", display_name="Other", created_by=other)
    WorkspaceMembership.objects.create(user=other, workspace=ws2, role=WorkspaceMembership.OWNER)
    foreign = Session.objects.create(workspace=ws2, created_by=other)
    r = client.get(f"/api/canopy-sessions/{foreign.id}")
    assert r.status_code == 404


def test_create_project_session(client):
    r = client.post("/api/canopy-sessions/", data={"project": "canopy-web"}, content_type="application/json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["agent_slug"] is None
    assert body["project"] == "canopy-web"


def test_create_rejects_agent_and_project_together(client):
    r = client.post(
        "/api/canopy-sessions/",
        data={"agent_slug": "echo", "project": "canopy-web"},
        content_type="application/json",
    )
    assert r.status_code == 422, r.content
