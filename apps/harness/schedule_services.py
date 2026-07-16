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


def serialize_schedule(schedule: AgentSchedule) -> dict:
    """The single serialized shape. REST builds ScheduleOut(**this); the MCP
    tools return it directly. fire_after = last_slot or created_at is the anchor
    the runner passes to due_slot — last_slot is NULL until the first fire, and
    an unbounded backward lookup would fire a slot predating the schedule."""
    latest = services.latest_occurrence_turn(schedule)
    return {
        "id": schedule.id,
        "agent_slug": schedule.agent_slug,
        "name": schedule.name,
        "prompt": schedule.prompt,
        "cron": schedule.cron,
        "timezone": schedule.timezone,
        "enabled": schedule.enabled,
        "routing": schedule.routing,
        "grace_minutes": schedule.grace_minutes,
        "notify": schedule.notify,
        "last_slot": schedule.last_slot,
        "fire_after": schedule.last_slot or schedule.created_at,
        "next_runs": next_slots(schedule.cron, schedule.timezone, now=timezone.now(), count=3),
        "last_status": latest.status if latest else "",
        "created_at": schedule.created_at,
        "updated_at": schedule.updated_at,
    }


def list_schedules(user, agent_slug: str, *, workspace_slug: str | None = None) -> list[AgentSchedule]:
    agent = _resolve_agent(user, agent_slug, workspace_slug=workspace_slug)
    return list(agent.schedules.all())


def create_schedule(
    user, agent_slug: str, fields: dict, *, workspace_slug: str | None = None
) -> AgentSchedule:
    agent = _resolve_agent(user, agent_slug, workspace_slug=workspace_slug)
    try:
        # Own savepoint: an IntegrityError from uniq_agent_schedule_name must not
        # poison the request transaction (SESSION_SAVE_EVERY_REQUEST would then
        # 400 instead of surfacing the 409). Mirrors apps/projects/api.py.
        with transaction.atomic():
            return AgentSchedule.objects.create(agent=agent, **fields)
    except IntegrityError:
        raise DuplicateScheduleName(fields["name"]) from None


def update_schedule(
    user, agent_slug: str, schedule_id: int, fields: dict, *, workspace_slug: str | None = None
) -> AgentSchedule:
    schedule = _resolve_schedule(user, agent_slug, schedule_id, workspace_slug=workspace_slug)
    for key, value in fields.items():
        setattr(schedule, key, value)
    if fields:
        try:
            with transaction.atomic():  # savepoint — see create_schedule
                schedule.save()
        except IntegrityError:
            raise DuplicateScheduleName(schedule.name) from None
    return schedule


def delete_schedule(
    user, agent_slug: str, schedule_id: int, *, workspace_slug: str | None = None
) -> None:
    """Retire open occurrences FIRST — see the module docstring and the spec.
    There is no Turn->AgentSchedule FK, so nothing cascades; an executing
    occurrence would otherwise hold one_executing_turn_per_agent forever."""
    schedule = _resolve_schedule(user, agent_slug, schedule_id, workspace_slug=workspace_slug)
    services.supersede_open_turns(schedule, reason="schedule deleted")
    schedule.delete()


def run_schedule_now(
    user, agent_slug: str, schedule_id: int, *, workspace_slug: str | None = None
) -> AgentSchedule:
    schedule = _resolve_schedule(user, agent_slug, schedule_id, workspace_slug=workspace_slug)
    services.run_schedule_now(schedule)
    return schedule


def preview_cron(
    user, agent_slug: str, cron: str, timezone_name: str, *, workspace_slug: str | None = None
) -> list[dt.datetime]:
    """agent_slug is for authorization only (you must see the agent to preview
    against it) — matches the REST preview route, which resolves + ignores it."""
    _resolve_agent(user, agent_slug, workspace_slug=workspace_slug)
    return next_slots(cron, timezone_name, now=timezone.now(), count=3)
