"""Django Ninja router for /api/agents/{slug}/schedules — the human-facing CRUD
for recurring turns.

Deliberately separate from api.py: that module is the machine control plane
(runner pairing, claim, lease), this one is the supervisor's editing surface.
Mounted on the /agents namespace exactly as agent_runs already is, so the
tenant path /api/w/{ws}/agents/... works via WorkspaceResolveMiddleware.
"""
from __future__ import annotations

from canopy_cron import next_slots
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Status
from ninja.errors import HttpError

from apps.api.auth import session_auth
from apps.api.errors import TYPE_CONFLICT, ProblemError
from apps.api.pagination import Page, clamp_limit, paginate

from . import services
from .api import _agent_or_404
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
    limit = clamp_limit(limit)
    items = [_serialize(s) for s in agent.schedules.all()]
    return paginate(items, offset=0, limit=limit)


def _duplicate_name(name: str) -> ProblemError:
    """uniq_agent_schedule_name is a DB constraint — an uncaught IntegrityError
    surfaces the UI's "New schedule" button (and Edit's rename) as a 500. 409 is
    what this repo already returns for a uniqueness violation (see
    apps/projects/api.py's slug conflict, apps/workspaces/api.py)."""
    return ProblemError(
        409,
        "Schedule name already exists",
        type_=TYPE_CONFLICT,
        detail=f"A schedule named '{name}' already exists for this agent.",
    )


@router.post("/{slug}/schedules/", response={201: ScheduleOut},
             summary="Create a recurring schedule",
             openapi_extra={"x-mcp-expose": True})
def create_schedule(request: HttpRequest, slug: str, payload: ScheduleIn) -> Status:
    agent = _agent_or_404(request, slug)
    fields = payload.dict()
    try:
        # Own atomic block (savepoint): an IntegrityError from
        # uniq_agent_schedule_name must not poison an outer transaction — the
        # session write SessionMiddleware makes on every response
        # (SESSION_SAVE_EVERY_REQUEST) would otherwise hit a broken connection
        # and 400 instead of the 409 below. Mirrors apps/projects/api.py.
        with transaction.atomic():
            schedule = AgentSchedule.objects.create(agent=agent, **fields)
    except IntegrityError:
        raise _duplicate_name(fields["name"]) from None
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
        try:
            with transaction.atomic():  # savepoint — see create_schedule
                schedule.save()
        except IntegrityError:
            raise _duplicate_name(schedule.name) from None
    return _serialize(schedule)


@router.delete("/{slug}/schedules/{schedule_id}", response={204: None},
               summary="Delete a recurring schedule",
               openapi_extra={"x-mcp-expose": True})
def delete_schedule(request: HttpRequest, slug: str, schedule_id: int) -> Status:
    """Deleting a schedule retires its open occurrences FIRST.

    There is no occurrence table — the Turn IS the occurrence, linked only by
    origin_ref["schedule_id"] — so nothing cascades. An executing occurrence
    holds one_executing_turn_per_agent, and release_stale_occurrence_turns_all()
    resolves schedules by id: delete the row and that turn becomes permanently
    unreleasable (the runner's heartbeat renews its lease, so the lease sweep
    never rescues it either), wedging every subsequent turn for the agent
    forever — with the nag that would surface it gone too. Superseding first also
    retires orphaned QUEUED occurrences, which would otherwise execute a prompt
    for a schedule that no longer exists.
    """
    schedule = _schedule_or_404(request, slug, schedule_id)
    services.supersede_open_turns(schedule, reason="schedule deleted")
    schedule.delete()
    return Status(204, None)


@router.post("/{slug}/schedules/{schedule_id}/run-now", response={202: ScheduleOut},
             summary="Trigger a schedule off-cycle, now",
             openapi_extra={"x-mcp-expose": True})
def run_now(request: HttpRequest, slug: str, schedule_id: int) -> Status:
    schedule = _schedule_or_404(request, slug, schedule_id)
    services.run_schedule_now(schedule)
    return Status(202, _serialize(schedule))
