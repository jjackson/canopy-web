"""Request-free schedule service layer.

The MCP invariant (apps/mcp/tools/insights.py) is that tools call the SAME
service functions as the REST views, so the two surfaces can't drift. Schedules
had no such layer — create/update/delete were inline in the Ninja handlers — so
this module extracts them. It takes a `user` (not a `request`) and raises domain
exceptions (not HttpError), so both the REST routes and the MCP tools can call
it. REST maps the exceptions to HTTP; the MCP re-raises them after auditing.

Reuses apps.harness.services for the turn-lifecycle operations
(supersede_open_turns / run_schedule_now / latest_occurrence_turn).
"""
from __future__ import annotations

import datetime as dt

from canopy_cron import next_slots
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.agents.models import Agent
from apps.workspaces import services as wsvc

from . import services
from .models import AgentSchedule


class ScheduleNotFound(Exception):
    """Agent missing / wrong tenant / non-member / schedule not under this agent.

    One type for all four, so a non-member cannot distinguish 'no such agent'
    from 'not yours' — existence never leaks."""


class DuplicateScheduleName(Exception):
    """The uniq_agent_schedule_name constraint was violated on create/update."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def _resolve_agent(user, agent_slug: str, *, workspace_slug: str | None = None) -> Agent:
    """Resolve an agent, gated by workspace membership. Request-free twin of
    apps/harness/api.py::_agent_or_404 — the tenant-URL pin is a parameter.

    REST passes request.workspace_slug (preserving today's behavior); the MCP
    passes None (membership gating only, no tenant-URL concept). Every failure
    raises ScheduleNotFound — 404-not-403 on the REST side, no existence leak."""
    agent = Agent.objects.filter(slug=agent_slug).first()
    if agent is None:
        raise ScheduleNotFound(agent_slug)
    wsvc.auto_join_workspaces(user)
    if workspace_slug and agent.workspace_id != workspace_slug:
        raise ScheduleNotFound(agent_slug)  # wrong tenant
    if agent.workspace_id and not wsvc.is_member(user, agent.workspace_id):
        raise ScheduleNotFound(agent_slug)
    return agent


def _resolve_schedule(
    user, agent_slug: str, schedule_id: int, *, workspace_slug: str | None = None
) -> AgentSchedule:
    agent = _resolve_agent(user, agent_slug, workspace_slug=workspace_slug)
    schedule = AgentSchedule.objects.filter(pk=schedule_id, agent=agent).first()
    if schedule is None:
        raise ScheduleNotFound(f"{agent_slug}/{schedule_id}")
    return schedule
