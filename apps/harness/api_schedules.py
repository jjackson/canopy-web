"""Django Ninja router for /api/agents/{slug}/schedules — the human-facing CRUD
for recurring turns.

Deliberately separate from api.py: that module is the machine control plane
(runner pairing, claim, lease), this one is the supervisor's editing surface.
Mounted on the /agents namespace exactly as agent_runs already is, so the
tenant path /api/w/{ws}/agents/... works via WorkspaceResolveMiddleware.

The handlers are thin: they resolve + serialize via schedule_services (the
request-free layer the MCP tools also call, so the two surfaces can't drift),
mapping its domain exceptions to HTTP — ScheduleNotFound -> 404, and
DuplicateScheduleName -> the repo's 409 uniqueness convention. The savepoint +
supersede logic lives in the service, so these handlers no longer touch the ORM.
"""
from __future__ import annotations

from django.http import HttpRequest
from ninja import Router, Status
from ninja.errors import HttpError

from apps.api.auth import session_auth
from apps.api.errors import TYPE_CONFLICT, ProblemError
from apps.api.pagination import Page, clamp_limit, paginate

from . import schedule_services as ss
from .schemas import (
    ScheduleIn,
    ScheduleOut,
    SchedulePatch,
    SchedulePreviewIn,
    SchedulePreviewOut,
)

router = Router(auth=session_auth, tags=["schedules"])


def _pin(request: HttpRequest) -> str | None:
    return getattr(request, "workspace_slug", None)


def _not_found(exc: ss.ScheduleNotFound) -> HttpError:
    return HttpError(404, "not found")


def _duplicate_name(name: str) -> ProblemError:
    """uniq_agent_schedule_name -> 409, the repo's convention for a uniqueness
    violation (apps/projects/api.py, apps/workspaces/api.py)."""
    return ProblemError(
        409,
        "Schedule name already exists",
        type_=TYPE_CONFLICT,
        detail=f"A schedule named '{name}' already exists for this agent.",
    )


@router.get("/{slug}/schedules/", response=Page[ScheduleOut],
            summary="List an agent's recurring schedules",
            openapi_extra={"x-mcp-expose": True})
def list_schedules(request: HttpRequest, slug: str, limit: int = 100) -> Page[ScheduleOut]:
    try:
        schedules = ss.list_schedules(request.user, slug, workspace_slug=_pin(request))
    except ss.ScheduleNotFound as exc:
        raise _not_found(exc) from None
    items = [ScheduleOut(**ss.serialize_schedule(s)) for s in schedules]
    return paginate(items, offset=0, limit=clamp_limit(limit))


@router.post("/{slug}/schedules/", response={201: ScheduleOut},
             summary="Create a recurring schedule",
             openapi_extra={"x-mcp-expose": True})
def create_schedule(request: HttpRequest, slug: str, payload: ScheduleIn) -> Status:
    try:
        schedule = ss.create_schedule(request.user, slug, payload.dict(), workspace_slug=_pin(request))
    except ss.ScheduleNotFound as exc:
        raise _not_found(exc) from None
    except ss.DuplicateScheduleName as exc:
        raise _duplicate_name(exc.name) from None
    return Status(201, ScheduleOut(**ss.serialize_schedule(schedule)))


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
    try:
        runs = ss.preview_cron(
            request.user, slug, payload.cron, payload.timezone, workspace_slug=_pin(request)
        )
    except ss.ScheduleNotFound as exc:
        raise _not_found(exc) from None
    return SchedulePreviewOut(next_runs=runs)


@router.patch("/{slug}/schedules/{schedule_id}", response=ScheduleOut,
              summary="Update a recurring schedule",
              openapi_extra={"x-mcp-expose": True})
def update_schedule(
    request: HttpRequest, slug: str, schedule_id: int, payload: SchedulePatch
) -> ScheduleOut:
    # exclude_none as well as exclude_unset: SchedulePatch's validators are
    # `validate_cron(v) if v is not None else v`, so an explicit {"cron": null}
    # slips past validation AND counts as "set" — setattr'ing None onto a
    # non-nullable column would 500 where a 422 belongs. No AgentSchedule field
    # is nullable via PATCH, so dropping None is always the right reading.
    fields = payload.dict(exclude_unset=True, exclude_none=True)
    try:
        schedule = ss.update_schedule(request.user, slug, schedule_id, fields, workspace_slug=_pin(request))
    except ss.ScheduleNotFound as exc:
        raise _not_found(exc) from None
    except ss.DuplicateScheduleName as exc:
        raise _duplicate_name(exc.name) from None
    return ScheduleOut(**ss.serialize_schedule(schedule))


@router.delete("/{slug}/schedules/{schedule_id}", response={204: None},
               summary="Delete a recurring schedule",
               openapi_extra={"x-mcp-expose": True})
def delete_schedule(request: HttpRequest, slug: str, schedule_id: int) -> Status:
    try:
        ss.delete_schedule(request.user, slug, schedule_id, workspace_slug=_pin(request))
    except ss.ScheduleNotFound as exc:
        raise _not_found(exc) from None
    return Status(204, None)


@router.post("/{slug}/schedules/{schedule_id}/run-now", response={202: ScheduleOut},
             summary="Trigger a schedule off-cycle, now",
             openapi_extra={"x-mcp-expose": True})
def run_now(request: HttpRequest, slug: str, schedule_id: int) -> Status:
    try:
        schedule = ss.run_schedule_now(request.user, slug, schedule_id, workspace_slug=_pin(request))
    except ss.ScheduleNotFound as exc:
        raise _not_found(exc) from None
    return Status(202, ScheduleOut(**ss.serialize_schedule(schedule)))
