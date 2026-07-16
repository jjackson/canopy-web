"""Request-free schedule service layer — auth resolution + CRUD, shared by the
REST routes and the MCP tools."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.agents.models import Agent
from apps.harness import schedule_services as ss
from apps.harness.models import AgentSchedule
from apps.workspaces import services as wsvc
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


@pytest.fixture()
def owner():
    return User.objects.create_user("jj", "jj@dimagi.com", "pw")


@pytest.fixture()
def ws(owner):
    w = Workspace.objects.create(
        slug="dimagi", display_name="Dimagi", created_by=owner, auto_join_domains=[]
    )
    wsvc.ensure_member(w, owner, WorkspaceMembership.OWNER)
    return w


@pytest.fixture()
def agent(ws):
    return Agent.objects.create(slug="eva", name="Eva", workspace=ws)


def test_resolve_agent_for_member(owner, agent):
    assert ss._resolve_agent(owner, "eva").slug == "eva"


def test_resolve_agent_missing_raises_not_found(owner, ws):
    with pytest.raises(ss.ScheduleNotFound):
        ss._resolve_agent(owner, "nope")


def test_resolve_agent_non_member_raises_not_found(agent):
    """A non-member gets ScheduleNotFound — the same as a missing agent, so
    tenancy never leaks existence."""
    outsider = User.objects.create_user("mallory", "mallory@evil.com", "pw")
    with pytest.raises(ss.ScheduleNotFound):
        ss._resolve_agent(outsider, "eva")


def test_resolve_agent_wrong_tenant_pin_raises_not_found(owner, agent):
    """The workspace_slug pin (the REST tenant-URL) must match the agent's."""
    with pytest.raises(ss.ScheduleNotFound):
        ss._resolve_agent(owner, "eva", workspace_slug="some-other-ws")


def test_resolve_schedule_wrong_agent_raises_not_found(owner, agent, ws):
    other = Agent.objects.create(slug="echo", name="Echo", workspace=ws)
    sched = AgentSchedule.objects.create(
        agent=other, name="s", prompt="p", cron="0 9 * * 5", timezone="UTC"
    )
    with pytest.raises(ss.ScheduleNotFound):
        ss._resolve_schedule(owner, "eva", sched.id)
