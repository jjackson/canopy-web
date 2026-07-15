"""The supervisor's home screen: one call for the whole fleet's needs-you."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.agents.models import Agent, AgentTask
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


@pytest.fixture()
def owner():
    return User.objects.create_user("owner", "owner@dimagi.com", "pw")


@pytest.fixture()
def workspace(owner):
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=owner)
    WorkspaceMembership.objects.create(user=owner, workspace=ws, role=WorkspaceMembership.OWNER)
    return ws


@pytest.fixture()
def client(owner):
    c = Client()
    c.force_login(owner)
    return c


def test_fleet_needs_you_sums_waiting_across_agents(client, workspace):
    echo = Agent.objects.create(slug="echo", name="Echo", workspace=workspace)
    hal = Agent.objects.create(slug="hal", name="Hal", workspace=workspace)
    AgentTask.objects.create(agent=echo, ext_id="t1", title="Draft a story", status="suggested")
    AgentTask.objects.create(agent=hal, ext_id="t2", title="Sweep security", status="suggested")

    resp = client.get("/api/agents/needs-you")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_waiting"] == 2
    assert {a["agent_slug"] for a in body["agents"]} == {"echo", "hal"}


def test_fleet_needs_you_ranks_busiest_agent_first(client, workspace):
    quiet = Agent.objects.create(slug="quiet", name="Quiet", workspace=workspace)
    busy = Agent.objects.create(slug="busy", name="Busy", workspace=workspace)
    AgentTask.objects.create(agent=quiet, ext_id="q1", title="One", status="suggested")
    for i in range(3):
        AgentTask.objects.create(agent=busy, ext_id=f"b{i}", title=f"Task {i}", status="suggested")

    body = client.get("/api/agents/needs-you").json()
    assert [a["agent_slug"] for a in body["agents"]] == ["busy", "quiet"]


def test_fleet_needs_you_excludes_other_tenants(client, owner):
    other_owner = User.objects.create_user("other", "other@example.org", "pw")
    other_ws = Workspace.objects.create(slug="other", display_name="Other", created_by=other_owner)
    secret = Agent.objects.create(slug="secret", name="Secret", workspace=other_ws)
    AgentTask.objects.create(agent=secret, ext_id="s1", title="Classified", status="suggested")

    body = client.get("/api/agents/needs-you").json()
    assert body["total_waiting"] == 0
    assert body["agents"] == []
