"""Django Ninja router for /api/harness — runner registry + turn lifecycle."""
from __future__ import annotations

import uuid

from django.http import HttpRequest
from ninja import Router
from ninja.errors import HttpError

from apps.agents.models import Agent
from apps.api.auth import session_auth
from apps.api.errors import ProblemError
from apps.workspaces import services as wsvc

from . import services
from .models import Runner, Turn
from .schemas import (
    HeartbeatIn,
    RecordSessionIn,
    ResolveSessionIn,
    ResolveSessionOut,
    RunnerIn,
    RunnerOut,
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


def _runner_or_404(runner_id: uuid.UUID) -> Runner:
    runner = Runner.objects.filter(pk=runner_id).exclude(status=Runner.RETIRED).first()
    if runner is None:
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
    wsvc.auto_join_workspaces(request.user)
    explicit = (payload.workspace or "").strip()
    if explicit:
        # Membership-gated: a missing workspace and a non-member get the same
        # 404 (no existence leak), exactly as apps/agents does on explicit homing.
        if not wsvc.is_member(request.user, explicit):
            raise HttpError(404, f"workspace '{explicit}' not found")
        ws_slug = explicit
    else:
        default = wsvc.user_default_workspace(request.user)
        ws_slug = default.slug if default else None
    runner = Runner.objects.create(
        name=payload.name,
        kind=payload.kind,
        capabilities=payload.capabilities,
        host=payload.host,
        paired_by=request.user,
        workspace_id=ws_slug,
    )
    return 201, runner


@router.post("/runners/{runner_id}/heartbeat", response=RunnerOut)
def runner_heartbeat(request: HttpRequest, runner_id: uuid.UUID, payload: HeartbeatIn):
    runner = _runner_or_404(runner_id)
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
    runner = _runner_or_404(runner_id)
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
    runner = _runner_or_404(runner_id)
    agent = Agent.objects.filter(slug=payload.agent_slug).first()
    if agent is None:
        raise HttpError(404, f"agent '{payload.agent_slug}' not found")
    return services.resolve_session(agent, payload.thread_key, runner)


@router.post("/runners/{runner_id}/record-session", response=ResolveSessionOut)
def record_session(request: HttpRequest, runner_id: uuid.UUID, payload: RecordSessionIn):
    """Upsert the durable link and point its live-session hint at THIS runner/host,
    after a session was created or reused for the thread. Returns the fresh resolution."""
    runner = _runner_or_404(runner_id)
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
