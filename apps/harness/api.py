"""Django Ninja router for /api/harness — runner registry + turn lifecycle."""
from __future__ import annotations

import uuid

from django.db.models import Q
from django.http import HttpRequest
from ninja import Router, Status
from ninja.errors import HttpError

from apps.agents.models import Agent
from apps.api.auth import session_auth
from apps.api.errors import ProblemError
from apps.api.pagination import Page, paginate
from apps.workspaces import services as wsvc

from . import services
from .models import AgentSchedule, Runner, Turn
from .schemas import (
    HeartbeatIn,
    RecordSessionIn,
    ResolveSessionIn,
    ResolveSessionOut,
    RunnerIn,
    RunnerOut,
    ScheduleFireIn,
    ScheduleOut,
    TurnEventCountOut,
    TurnEventsIn,
    TurnEventsOut,
    TurnFinishIn,
    TurnIn,
    TurnOut,
    TurnStartIn,
)

router = Router(auth=session_auth, tags=["harness"])

# Allowed values for TurnEvent.kind. Kept in sync with the event kinds the
# runner/agent side actually emits; anything else 422s at the API boundary
# rather than being silently persisted.
ALLOWED_EVENT_KINDS = {
    "status",
    "assistant",
    "tool_start",
    "tool_end",
    "question",
    "approval",
    "error",
    "heartbeat",
}


def _agent_or_404(request: HttpRequest, slug: str) -> Agent:
    """Resolve an agent, gated by workspace membership. A non-member gets the
    same 404 as a missing agent (no existence leak). Domain users are auto-joined
    to the agent's workspace first, so the default-workspace case keeps working.

    Harness-local twin of agents.api._get_agent_or_404 — deliberately duplicated
    rather than imported: api modules must not depend on each other, and the
    harness is framework-tier.
    """
    agent = Agent.objects.filter(slug=slug).first()
    if agent is None:
        raise HttpError(404, f"agent '{slug}' not found")
    wsvc.auto_join_workspaces(request.user)
    ws = getattr(request, "workspace_slug", None)
    if ws and agent.workspace_id != ws:
        raise HttpError(404, f"agent '{slug}' not found")  # wrong tenant
    if agent.workspace_id and not wsvc.is_member(request.user, agent.workspace_id):
        raise HttpError(404, f"agent '{slug}' not found")
    return agent


def _runner_or_404(request: HttpRequest, runner_id: uuid.UUID) -> Runner:
    """Resolve a runner, pinned to the user who paired it. A runner may only be
    operated by its pairer; anyone else gets the same 404 as a missing runner (no
    existence leak), exactly like _agent_or_404.

    Without this pin, runner_id — a caller-supplied query param — is the whole
    authorization story, and any route deriving its tenant from runner.paired_by
    lets an attacker simply CHOOSE whose paired_by is read by passing someone
    else's runner_id. UUID4 unguessability is not an authorization check: the id
    travels in query strings, which proxies log.

    paired_by is nullable (on_delete=SET_NULL), and NULL must fail closed — the
    != below is True for None, so an orphaned runner is operable by nobody.
    """
    runner = Runner.objects.filter(pk=runner_id).exclude(status=Runner.RETIRED).first()
    if runner is None:
        raise HttpError(404, "runner not found")
    if runner.paired_by_id != request.user.id:
        raise HttpError(404, "runner not found")
    return runner


def _turn_or_404(turn_id: uuid.UUID) -> Turn:
    turn = Turn.objects.select_related("agent", "claimed_by").filter(pk=turn_id).first()
    if turn is None:
        raise HttpError(404, "turn not found")
    return turn


@router.post("/runners/", response={201: RunnerOut})
def pair_runner(request: HttpRequest, payload: RunnerIn):
    if payload.kind not in dict(Runner.KIND_CHOICES):
        raise HttpError(422, f"unknown runner kind '{payload.kind}'")
    runner = Runner.objects.create(
        name=payload.name,
        kind=payload.kind,
        capabilities=payload.capabilities,
        host=payload.host,
        paired_by=request.user,
    )
    return 201, runner


@router.post("/runners/{runner_id}/heartbeat", response=RunnerOut)
def runner_heartbeat(request: HttpRequest, runner_id: uuid.UUID, payload: HeartbeatIn):
    runner = _runner_or_404(request, runner_id)
    if payload.host and payload.host != runner.host:
        runner.host = payload.host
        runner.save(update_fields=["host"])
    return services.heartbeat(
        runner,
        active_turn_ids=payload.active_turn_ids,
        degraded=payload.degraded,
        note=payload.note,
    )


@router.post("/runners/{runner_id}/claim", response={200: TurnOut, 204: None})
def claim_turn(request: HttpRequest, runner_id: uuid.UUID, paused: str = ""):
    """Claim the next eligible turn. `paused` is an optional comma-separated list of
    agent slugs the caller has locally paused (per-agent pause) — the server skips
    their queued turns so nothing is claimed-then-released. Omitted by older runners
    (backward-compatible: no exclusions)."""
    runner = _runner_or_404(request, runner_id)
    exclude = [s for s in (p.strip() for p in paused.split(",")) if s]
    turn = services.claim_next_turn(runner, exclude_slugs=exclude or None)
    if turn is None:
        return 204, None
    return 200, turn


@router.post("/runners/{runner_id}/resolve-session", response=ResolveSessionOut)
def resolve_session(request: HttpRequest, runner_id: uuid.UUID, payload: ResolveSessionIn):
    """Given (agent, thread_key), tell THIS runner whether it can reuse an existing
    emdash session (it owns the live hint) or must spawn fresh + rehydrate context.
    Runner-scoped because reuse depends on the caller's macOS host."""
    runner = _runner_or_404(request, runner_id)
    agent = Agent.objects.filter(slug=payload.agent_slug).first()
    if agent is None:
        raise HttpError(404, f"agent '{payload.agent_slug}' not found")
    return services.resolve_session(agent, payload.thread_key, runner)


@router.post("/runners/{runner_id}/record-session", response=ResolveSessionOut)
def record_session(request: HttpRequest, runner_id: uuid.UUID, payload: RecordSessionIn):
    """Upsert the durable link and point its live-session hint at THIS runner/host,
    after a session was created or reused for the thread. Returns the fresh resolution."""
    runner = _runner_or_404(request, runner_id)
    agent = Agent.objects.filter(slug=payload.agent_slug).first()
    if agent is None:
        raise HttpError(404, f"agent '{payload.agent_slug}' not found")
    services.record_session(
        agent, payload.thread_key, runner=runner,
        emdash_task_id=payload.emdash_task_id, session_id=payload.session_id,
        agent_task_ext_id=payload.agent_task_ext_id, summary=payload.summary,
    )
    return services.resolve_session(agent, payload.thread_key, runner)


@router.post("/turns/", response={200: TurnOut, 201: TurnOut})
def enqueue_turn(request: HttpRequest, payload: TurnIn):
    agent = Agent.objects.filter(slug=payload.agent_slug).first()
    if agent is None:
        raise HttpError(404, f"agent '{payload.agent_slug}' not found")
    if payload.origin not in dict(Turn.ORIGIN_CHOICES):
        raise HttpError(422, f"unknown origin '{payload.origin}'")
    if payload.routing not in dict(Turn.ROUTING_CHOICES):
        raise HttpError(422, f"unknown routing '{payload.routing}'")
    turn, created = services.enqueue_turn(
        agent=agent,
        origin=payload.origin,
        idempotency_key=payload.idempotency_key,
        prompt=payload.prompt,
        origin_ref=payload.origin_ref,
        routing=payload.routing,
    )
    return (201 if created else 200), turn


@router.get("/turns/", response=list[TurnOut])
def list_turns(request: HttpRequest, agent: str | None = None, status: str | None = None):
    qs = Turn.objects.select_related("agent", "claimed_by").order_by("-created_at")
    if agent:
        qs = qs.filter(agent__slug=agent)
    if status:
        qs = qs.filter(status__in=status.split(","))
    return list(qs[:100])  # filter BEFORE slicing — a sliced queryset cannot be filtered


@router.get("/turns/{turn_id}", response=TurnOut)
def get_turn(request: HttpRequest, turn_id: uuid.UUID):
    return _turn_or_404(turn_id)


@router.post("/turns/{turn_id}/events", response=TurnEventCountOut)
def append_turn_events(request: HttpRequest, turn_id: uuid.UUID, payload: TurnEventsIn):
    turn = _turn_or_404(turn_id)
    for event in payload.events:
        if event.kind not in ALLOWED_EVENT_KINDS:
            raise HttpError(422, f"unknown event kind '{event.kind}'")
    count = services.append_events(turn, [e.dict() for e in payload.events])
    return {"count": count}


@router.get("/turns/{turn_id}/events", response=TurnEventsOut)
def read_turn_events(request: HttpRequest, turn_id: uuid.UUID, after: int = 0):
    turn = _turn_or_404(turn_id)
    events = turn.events.filter(seq__gt=after).order_by("seq")[:500]
    return {"events": list(events)}


@router.post("/turns/{turn_id}/start", response=TurnOut)
def start_turn(request: HttpRequest, turn_id: uuid.UUID, payload: TurnStartIn):
    turn = _turn_or_404(turn_id)
    if turn.status not in (Turn.CLAIMED, Turn.RUNNING):
        raise ProblemError(409, "Turn not startable", detail=f"status={turn.status}")
    return services.mark_running(turn, session_id=payload.session_id)


@router.post("/turns/{turn_id}/finish", response=TurnOut)
def finish_turn(request: HttpRequest, turn_id: uuid.UUID, payload: TurnFinishIn):
    turn = _turn_or_404(turn_id)
    if payload.status not in (Turn.DONE, Turn.FAILED):
        raise HttpError(422, "finish status must be done|failed")
    if turn.status in Turn.TERMINAL:
        return turn  # idempotent finish
    result = services.finish_turn(turn, status=payload.status, result_note=payload.result_note)
    if result.status not in Turn.TERMINAL:
        # services.finish_turn only transitions claimed/running/needs_human — a
        # queued turn is a silent no-op there. Surface that as a 409 instead of
        # returning a turn that looks unchanged.
        raise ProblemError(409, "Turn not finishable", detail=f"status={result.status}")
    return result


# --------------------------------------------------------------------------------------
# AgentSchedule — the runner-facing half. The supervisor's CRUD lives in api_schedules.py;
# these two routes are what the laptop daemon actually calls: sync, then report a due slot.
# --------------------------------------------------------------------------------------

def _runner_schedule_qs(runner: Runner):
    """Schedules this runner may see, gated by TENANT — never by capabilities.

    capabilities is a caller-supplied routing hint declared at pairing and never
    validated (see b4f5ead, Critical): scoping by it would let anyone pair a
    runner declaring a victim's agent slug and read that agent's schedules,
    leaking `prompt`. The workspace is the boundary.

    The tenant is derived from `paired_by` — the human who paired the runner —
    rather than a Runner.workspace field, deliberately:
      * Runner.workspace does not exist on main; it is added by the concurrent
        canopy-mobile branch (0004_runner_workspace). Adding it here would
        collide with that migration for no gain.
      * paired_by is server-assigned at pairing (request.user), so the FIELD is
        not attacker-controlled.

    That last point is necessary but NOT sufficient, and reading it alone is how
    this route was first shipped vulnerable. Deriving the tenant from an
    unspoofable field on a row the ATTACKER SELECTED buys nothing: runner_id is
    a caller-supplied query param, so choosing whose paired_by gets read is as
    good as spoofing it. The real invariant needs both halves — the tenant
    derives from paired_by AND _runner_or_404 pins the runner to request.user,
    so the row and the field are alike server-controlled.

    When Runner.workspace lands, this may narrow to it; the predicate below is
    the conservative superset of that rule, never a wider one.
    """
    qs = AgentSchedule.objects.filter(enabled=True).select_related("agent")
    if runner.paired_by_id is None:
        return qs.none()  # an orphaned runner has no identity to derive tenancy from
    slugs = wsvc.user_workspace_slugs(runner.paired_by)
    # Same-tenant agents, or legacy null-workspace agents (the pre-tenancy path
    # the existing suite covers). claim_next_turn has no workspace predicate on
    # this branch; the INCOMING b4f5ead adds one of this shape, and this should
    # converge with it on merge. Until then the invariant holds HERE, not fleet-wide.
    return qs.filter(Q(agent__workspace_id__in=slugs) | Q(agent__workspace_id__isnull=True))


@router.get("/schedules/", response=Page[ScheduleOut],
            summary="Schedules this runner may fire (tenant-scoped)")
def sync_schedules(request: HttpRequest, runner_id: uuid.UUID, limit: int = 200) -> Page[ScheduleOut]:
    """The runner's schedule sync. It caches these locally, evaluates the cron
    itself, and POSTs /fire when a slot comes due.

    Deliberately NOT gated on Runner.ONLINE, unlike claim_next_turn: ONLINE gates
    claiming because claiming ASSIGNS work and takes the one_executing_turn_per_agent
    lock, so an offline claimer would wedge the agent. Sync is a read, and fire only
    produces a QUEUED turn (which stacks freely and is executed by whichever ONLINE
    runner in the tenant claims it). Gating here would impose a boot-order dependency
    — a fresh daemon would have to sync before its first heartbeat.
    """
    # Imported inside to dodge a real cycle: api_schedules imports .api at module level.
    from .api_schedules import _serialize

    runner = _runner_or_404(request, runner_id)
    items = [_serialize(s) for s in _runner_schedule_qs(runner)]
    # max(1, ...): Page.limit is Field(ge=1, le=500), so an unfloored limit=0 or
    # negative raises inside the response model — a 500 where a 422 belongs.
    return paginate(items, offset=0, limit=max(1, min(limit, 500)))


@router.post("/schedules/{schedule_id}/fire", response={201: TurnOut},
             summary="Report a due slot; the server materializes the turn")
def fire_schedule_route(
    request: HttpRequest, schedule_id: int, runner_id: uuid.UUID, payload: ScheduleFireIn
) -> Status:
    runner = _runner_or_404(request, runner_id)
    schedule = _runner_schedule_qs(runner).filter(pk=schedule_id).first()
    if schedule is None:
        # 404 whether it is missing, disabled, or another tenant's — no existence leak.
        raise HttpError(404, f"schedule {schedule_id} not found")
    # Deliberately does NOT call release_stale_occurrence_turns: fire_schedule already
    # supersedes every open occurrence, so release would add nothing here except
    # a self-destruct on same-slot re-fire (fire skips supersede when the key
    # exists, but release would already have killed the turn this route returns).
    # Release runs on the CLAIM tick instead — see claim_next_turn.
    turn, _ = services.fire_schedule(schedule, payload.slot)
    return Status(201, turn)
