"""Django Ninja router for /api/agents/{slug}/schedules — the human-facing CRUD
for recurring turns.

Deliberately separate from api.py: that module is the machine control plane
(runner pairing, claim, lease), this one is the supervisor's editing surface.
Mounted on the /agents namespace exactly as agent_runs already is, so the
tenant path /api/w/{ws}/agents/... works via WorkspaceResolveMiddleware.
"""
from __future__ import annotations

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Status
from ninja.errors import HttpError

from apps.api.auth import session_auth
from apps.api.pagination import Page, paginate

from . import services
from .api import _agent_or_404
from .cron import next_slots
from .models import AgentSchedule
from .schemas import (
    ScheduleIn,
    ScheduleOut,
    SchedulePatch,
    SchedulePreviewIn,
    SchedulePreviewOut,
)

router = Router(auth=session_auth, tags=["schedules"])


def _serialize(schedule: AgentSchedule) -> ScheduleOut:
    latest = services.latest_occurrence_turn(schedule)
    return ScheduleOut(
        id=schedule.id,
        agent_slug=schedule.agent_slug,
        name=schedule.name,
        prompt=schedule.prompt,
        cron=schedule.cron,
        timezone=schedule.timezone,
        enabled=schedule.enabled,
        routing=schedule.routing,
        grace_minutes=schedule.grace_minutes,
        notify=schedule.notify,
        last_slot=schedule.last_slot,
        # last_slot is NULL until the first fire. Falling back to created_at is
        # what stops a fresh schedule from firing for a slot that predates it.
        fire_after=schedule.last_slot or schedule.created_at,
        next_runs=next_slots(schedule.cron, schedule.timezone, now=timezone.now(), count=3),
        last_status=latest.status if latest else "",
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


def _schedule_or_404(request: HttpRequest, slug: str, schedule_id: int) -> AgentSchedule:
    agent = _agent_or_404(request, slug)
    schedule = AgentSchedule.objects.filter(pk=schedule_id, agent=agent).first()
    if schedule is None:
        raise HttpError(404, f"schedule {schedule_id} not found")
    return schedule


@router.get("/{slug}/schedules/", response=Page[ScheduleOut],
            summary="List an agent's recurring schedules",
            openapi_extra={"x-mcp-expose": True})
def list_schedules(request: HttpRequest, slug: str, limit: int = 100) -> Page[ScheduleOut]:
    agent = _agent_or_404(request, slug)
    limit = min(limit, 500)
    items = [_serialize(s) for s in agent.schedules.all()]
    return paginate(items, offset=0, limit=limit)


@router.post("/{slug}/schedules/", response={201: ScheduleOut},
             summary="Create a recurring schedule",
             openapi_extra={"x-mcp-expose": True})
def create_schedule(request: HttpRequest, slug: str, payload: ScheduleIn) -> Status:
    agent = _agent_or_404(request, slug)
    schedule = AgentSchedule.objects.create(agent=agent, **payload.dict())
    return Status(201, _serialize(schedule))


# Route-ordering invariant: this literal "preview" route must stay declared
# BEFORE the "/{slug}/schedules/{schedule_id}" routes below. Django Ninja
# compiles path params with no int: converter, so "agents/echo/schedules/preview"
# resolves as {"schedule_id": "preview"} once a {schedule_id} pattern exists —
# and Django's URL resolution is method-agnostic (POST vs PATCH/DELETE doesn't
# disambiguate), so only declaration order keeps this route reachable. Moving
# this block below PATCH/DELETE would silently shadow it.
@router.post("/{slug}/schedules/preview", response=SchedulePreviewOut,
             summary="Preview the next fire times for a cron expression",
             openapi_extra={"x-mcp-expose": True})
def preview_schedule(
    request: HttpRequest, slug: str, payload: SchedulePreviewIn
) -> SchedulePreviewOut:
    """Answer 'when would this actually run?' at edit time. Computed with the same
    next_slots() the firing path uses — the client must never re-implement cron."""
    _agent_or_404(request, slug)
    return SchedulePreviewOut(
        next_runs=next_slots(payload.cron, payload.timezone, now=timezone.now(), count=3)
    )


@router.patch("/{slug}/schedules/{schedule_id}", response=ScheduleOut,
              summary="Update a recurring schedule",
              openapi_extra={"x-mcp-expose": True})
def update_schedule(
    request: HttpRequest, slug: str, schedule_id: int, payload: SchedulePatch
) -> ScheduleOut:
    schedule = _schedule_or_404(request, slug, schedule_id)
    # exclude_none as well as exclude_unset: SchedulePatch's validators are
    # `validate_cron(v) if v is not None else v`, so an explicit {"cron": null}
    # slips past validation AND counts as "set" — setattr'ing None onto a
    # non-nullable column would 500 where a 422 belongs. No AgentSchedule field
    # is nullable via PATCH, so dropping None is always the right reading.
    fields = payload.dict(exclude_unset=True, exclude_none=True)
    for key, value in fields.items():
        setattr(schedule, key, value)
    if fields:
        schedule.save()
    return _serialize(schedule)


@router.delete("/{slug}/schedules/{schedule_id}", response={204: None},
               summary="Delete a recurring schedule",
               openapi_extra={"x-mcp-expose": True})
def delete_schedule(request: HttpRequest, slug: str, schedule_id: int) -> Status:
    schedule = _schedule_or_404(request, slug, schedule_id)
    schedule.delete()
    return Status(204, None)


@router.post("/{slug}/schedules/{schedule_id}/run-now", response={202: ScheduleOut},
             summary="Trigger a schedule off-cycle, now",
             openapi_extra={"x-mcp-expose": True})
def run_now(request: HttpRequest, slug: str, schedule_id: int) -> Status:
    schedule = _schedule_or_404(request, slug, schedule_id)
    services.run_schedule_now(schedule)
    return Status(202, _serialize(schedule))
