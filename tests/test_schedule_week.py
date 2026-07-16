"""GET /api/agents/schedules/week — personal roll-up (flat) + tenant scope (pinned)."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.agents.models import Agent
from apps.harness import schedule_services as ss
from apps.workspaces import services as wsvc
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db

START = "2026-07-13T00:00:00Z"


def _ws(slug, owner):
    w = Workspace.objects.create(slug=slug, display_name=slug, created_by=owner, auto_join_domains=[])
    wsvc.ensure_member(w, owner, WorkspaceMembership.OWNER)
    return w


@pytest.fixture()
def setup():
    owner = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    a = _ws("alpha", owner)
    b = _ws("beta", owner)
    # A third workspace the owner is NOT a member of.
    stranger = User.objects.create_user("s", "s@x.com", "pw")
    c = Workspace.objects.create(slug="gamma", display_name="g", created_by=stranger, auto_join_domains=[])
    ea = Agent.objects.create(slug="eva", name="Eva", workspace=a)
    hb = Agent.objects.create(slug="hal", name="Hal", workspace=b)
    gc = Agent.objects.create(slug="ghost", name="Ghost", workspace=c)
    ss.create_schedule(owner, "eva", dict(name="A", prompt="p", cron="0 9 * * *", timezone="UTC",
                                          enabled=True, routing="prefer_local", grace_minutes=120, notify=["inbox"]))
    ss.create_schedule(owner, "hal", dict(name="B", prompt="p", cron="0 9 * * *", timezone="UTC",
                                          enabled=True, routing="prefer_local", grace_minutes=120, notify=["inbox"]))
    # ghost's schedule is created directly (owner can't via service — not a member)
    from apps.harness.models import AgentSchedule
    AgentSchedule.objects.create(agent=gc, name="C", prompt="p", cron="0 9 * * *", timezone="UTC")
    c_ = Client(); c_.force_login(owner)
    return c_


def test_personal_flat_spans_all_my_workspaces(setup):
    resp = setup.get(f"/api/agents/schedules/week?start={START}")
    assert resp.status_code == 200, resp.content
    names = {i["schedule"]["name"] for i in resp.json()["items"]}
    assert names == {"A", "B"}  # alpha + beta; NOT ghost's C (gamma, not a member)


def test_tenant_pinned_returns_one_workspace(setup):
    resp = setup.get(f"/api/w/alpha/agents/schedules/week?start={START}")
    assert resp.status_code == 200, resp.content
    names = {i["schedule"]["name"] for i in resp.json()["items"]}
    assert names == {"A"}  # alpha only


def test_fires_present_in_the_week(setup):
    resp = setup.get(f"/api/agents/schedules/week?start={START}")
    item = next(i for i in resp.json()["items"] if i["schedule"]["name"] == "A")
    # daily; the window over-fetches 8 days so no local-day fire is dropped on a
    # DST week (the client's dayIdx<7 guard trims the surplus back to 7 columns).
    assert len(item["fires"]) == 8
    assert item["workspace_slug"] == "alpha"
