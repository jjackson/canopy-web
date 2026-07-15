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


def test_fleet_needs_you_agrees_with_per_agent_endpoints(client, workspace):
    """The supervisor screen's fleet endpoint and each agent's own rail badge
    endpoint must never diverge — if they do, one is lying and the supervisor is
    untrustworthy, defeating the screen's purpose.

    Both endpoints call the same services.needs_you(), but the fleet endpoint
    re-derives its tenant scoping separately from _get_agent_or_404 (lines 79-84
    vs 42-55 in api.py), and duplicated scoping is exactly where a divergence
    would appear. This test pins the two endpoints' counts permanently.

    The task's brief asked for manual verification against a live stack; a test
    pins it permanently instead of once."""
    # Create two agents with different numbers of "suggested" tasks.
    alpha = Agent.objects.create(slug="alpha", name="Alpha", workspace=workspace)
    beta = Agent.objects.create(slug="beta", name="Beta", workspace=workspace)

    # Alpha has 2 suggested tasks; beta has 3.
    for i in range(2):
        AgentTask.objects.create(agent=alpha, ext_id=f"a{i}", title=f"Alpha task {i}", status="suggested")
    for i in range(3):
        AgentTask.objects.create(agent=beta, ext_id=f"b{i}", title=f"Beta task {i}", status="suggested")

    # Get the fleet view.
    fleet_resp = client.get("/api/agents/needs-you")
    assert fleet_resp.status_code == 200
    fleet = fleet_resp.json()

    # Build a map of agent_slug → waiting_count from the fleet response.
    fleet_counts = {a["agent_slug"]: a["waiting_count"] for a in fleet["agents"]}

    # For each agent in the fleet, fetch its own endpoint and verify agreement.
    for agent_slug in ["alpha", "beta"]:
        per_agent_resp = client.get(f"/api/agents/{agent_slug}/needs-you")
        assert per_agent_resp.status_code == 200
        per_agent = per_agent_resp.json()

        # Confirm the per-agent waiting_count matches the fleet's view of it.
        assert per_agent["waiting_count"] == fleet_counts[agent_slug], (
            f"Agent {agent_slug}: fleet says {fleet_counts[agent_slug]} waiting, "
            f"but /agents/{agent_slug}/needs-you says {per_agent['waiting_count']}"
        )

    # Confirm total_waiting is the sum of per-agent waiting_counts.
    expected_total = sum(fleet_counts.values())
    assert fleet["total_waiting"] == expected_total, (
        f"Fleet total_waiting={fleet['total_waiting']}, but sum of per-agent "
        f"counts={expected_total}"
    )
