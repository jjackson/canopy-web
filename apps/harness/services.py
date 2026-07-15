"""Harness domain services — the only write path for Runner/Turn/TurnEvent.

Claiming is a single conditional UPDATE (no row can be claimed twice); leases
are renewed by runner heartbeats and swept lazily on claim. All functions are
synchronous and transaction-safe.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from .models import AgentSchedule, Runner, SessionLink, Turn, TurnEvent

logger = logging.getLogger(__name__)

DEFAULT_LEASE_SECONDS = 900
HEARTBEAT_ONLINE_WINDOW = dt.timedelta(seconds=90)


def enqueue_turn(
    *,
    agent,
    origin: str,
    idempotency_key: str,
    prompt: str = "",
    origin_ref: dict | None = None,
    routing: str = Turn.PREFER_LOCAL,
) -> tuple[Turn, bool]:
    """Queued turns stack freely — the executing-turn index never blocks intake
    (new turns are born `queued`, which the index does not cover)."""
    existing = Turn.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            turn = Turn.objects.create(
                agent=agent,
                origin=origin,
                idempotency_key=idempotency_key,
                prompt=prompt,
                origin_ref=origin_ref or {},
                routing=routing,
            )
    except IntegrityError:
        # Only possible race: same idempotency key inserted concurrently.
        replay = Turn.objects.filter(idempotency_key=idempotency_key).first()
        if replay is not None:
            return replay, False
        raise
    return turn, True


def heartbeat(
    runner: Runner, *, active_turn_ids: list[str], degraded: bool = False, note: str = ""
) -> Runner:
    now = timezone.now()
    runner.last_heartbeat_at = now
    runner.status = Runner.DEGRADED if degraded else Runner.ONLINE
    runner.status_note = note
    runner.save(update_fields=["last_heartbeat_at", "status", "status_note"])
    if active_turn_ids:
        Turn.objects.filter(
            pk__in=active_turn_ids,
            claimed_by=runner,
            status__in=[Turn.CLAIMED, Turn.RUNNING, Turn.NEEDS_HUMAN],
        ).update(lease_expires_at=now + dt.timedelta(seconds=DEFAULT_LEASE_SECONDS))
    return runner


def sweep_expired_leases() -> int:
    now = timezone.now()
    expired = list(
        Turn.objects.filter(
            status__in=[Turn.CLAIMED, Turn.RUNNING, Turn.NEEDS_HUMAN],
            lease_expires_at__lt=now,
        )
    )
    count = 0
    for turn in expired:
        updated = Turn.objects.filter(pk=turn.pk, lease_expires_at__lt=now).exclude(
            status__in=Turn.TERMINAL
        ).update(status=Turn.LOST, finished_at=now)
        if updated:
            append_events(turn, [{"kind": "status", "payload": {"status": Turn.LOST, "reason": "lease_expired"}}])
            count += 1
    return count


def _kind_allows(runner: Runner, routing: str) -> bool:
    if routing == Turn.LOCAL_ONLY:
        return runner.kind in (Runner.EMDASH, Runner.REMOTE)
    return True


EXECUTING = [Turn.CLAIMED, Turn.RUNNING, Turn.NEEDS_HUMAN]


def claim_next_turn(runner: Runner, *, lease_seconds: int = DEFAULT_LEASE_SECONDS,
                    exclude_slugs: list[str] | None = None) -> Turn | None:
    if runner.status != Runner.ONLINE:
        return None
    sweep_expired_leases()
    # Lazy sweeps, both BEFORE the busy_agents read: a turn released here frees
    # its agent for the very claim we are about to make.
    release_stale_occurrence_turns_all()
    slugs = runner.agent_slugs()
    if exclude_slugs:
        # Per-agent pause: the runner locally paused these agents; never claim their
        # queued turns (they stay QUEUED, resumed the moment the pause is lifted).
        slugs = [s for s in slugs if s not in set(exclude_slugs)]
    if not slugs:
        return None
    routing_q = Q(routing__in=[Turn.PREFER_LOCAL, Turn.LOCAL_ONLY, Turn.ANY])
    if runner.kind == Runner.CLOUD:
        routing_q = Q(routing=Turn.ANY) | Q(routing=Turn.PREFER_LOCAL)
        # prefer_local turns fall to cloud only via the Phase 2 router policy;
        # Phase 0 has no cloud runners, so keep the simple rule: cloud never
        # takes local_only.
    busy_agents = Turn.objects.filter(status__in=EXECUTING).values("agent_id")
    # Tenant boundary: capabilities is a caller-supplied routing hint, not a
    # security boundary (a caller can declare whatever agent slugs it likes at
    # pairing). The workspace is the actual gate, applied as an intersection
    # with the capabilities filter above, not an alternative to it. A tenanted
    # runner may only claim turns whose agent is in that same workspace, or
    # whose agent predates tenancy (null workspace — the legacy-ungated path).
    # An untenanted runner may only claim turns whose agent is ALSO untenanted
    # — this null<->null rule is what keeps the pre-tenancy test suite (runner
    # + agent both created with no workspace) working without opening a hole.
    # Mirrors the same Q-based tenant filter in api.py::list_turns.
    if runner.workspace_id:
        tenant_q = Q(agent__workspace_id=runner.workspace_id) | Q(agent__workspace_id__isnull=True)
    else:
        tenant_q = Q(agent__workspace_id__isnull=True)
    candidates = (
        Turn.objects.filter(status=Turn.QUEUED, agent__slug__in=slugs)
        .exclude(agent_id__in=busy_agents)
        .filter(routing_q)
        .filter(tenant_q)
        .order_by("created_at")
    )
    now = timezone.now()
    for turn in candidates:
        if not _kind_allows(runner, turn.routing):
            continue
        try:
            # Own atomic block per attempt: an IntegrityError from the
            # one_executing_turn_per_agent index (concurrent claim for the
            # same agent) must not poison an outer transaction.
            with transaction.atomic():
                updated = Turn.objects.filter(pk=turn.pk, status=Turn.QUEUED).update(
                    status=Turn.CLAIMED,
                    claimed_by=runner,
                    claimed_at=now,
                    lease_expires_at=now + dt.timedelta(seconds=lease_seconds),
                )
        except IntegrityError:
            continue  # another runner claimed for this agent between our check and update
        if updated:
            turn.refresh_from_db()
            append_events(turn, [{"kind": "status", "payload": {"status": Turn.CLAIMED, "runner": runner.name}}])
            return turn
    return None


def append_events(turn: Turn, events: list[dict]) -> int:
    with transaction.atomic():
        # Lock the turn row first so concurrent appenders to the same turn
        # serialize on the Max("seq") read instead of racing each other into
        # the turnevent_seq_unique_per_turn index (sqlite ignores
        # select_for_update; Postgres serializes — that's the point).
        Turn.objects.select_for_update().get(pk=turn.pk)
        current = (
            TurnEvent.objects.filter(turn=turn).aggregate(m=Max("seq"))["m"] or 0
        )
        rows = [
            TurnEvent(turn=turn, seq=current + i + 1, kind=e["kind"], payload=e.get("payload", {}))
            for i, e in enumerate(events)
        ]
        TurnEvent.objects.bulk_create(rows)
    return len(rows)


def mark_running(turn: Turn, *, session_id: str = "") -> Turn:
    """Transition CLAIMED|RUNNING -> RUNNING. A no-op (no event, no field
    writes) if the turn was swept to a terminal state (e.g. lost) underneath
    the caller — guards against a zombie runner resurrecting a dead turn."""
    now = timezone.now()
    fields: dict = {"status": Turn.RUNNING}
    if not turn.started_at:
        fields["started_at"] = now
    if session_id:
        fields["session_id"] = session_id
    updated = Turn.objects.filter(
        pk=turn.pk, status__in=[Turn.CLAIMED, Turn.RUNNING]
    ).update(**fields)
    turn.refresh_from_db()
    if not updated:
        return turn
    append_events(turn, [{"kind": "status", "payload": {"status": Turn.RUNNING}}])
    return turn


def finish_turn(
    turn: Turn, *, status: str, result_note: str = "", allow_queued: bool = False
) -> Turn:
    """Transition CLAIMED|RUNNING|NEEDS_HUMAN -> DONE|FAILED|MISSED. A no-op (no
    event, no field writes) if the turn is already terminal — idempotent, and
    guards against resurrecting a turn already swept to lost.

    A QUEUED turn is deliberately NOT finishable by default: a runner must never
    finish a turn it never claimed (the API surfaces that attempt as a 409).
    `allow_queued=True` is the scheduler's opt-in — it is a different actor, and
    a slot nobody ever picked up is the textbook MISSED. Without it, supersede
    would silently skip queued occurrences and the board would accumulate them.
    """
    if status not in (Turn.DONE, Turn.FAILED, Turn.MISSED):
        raise ValueError(f"finish status must be done|failed|missed, got {status!r}")
    now = timezone.now()
    from_states = [Turn.CLAIMED, Turn.RUNNING, Turn.NEEDS_HUMAN]
    if allow_queued:
        from_states.append(Turn.QUEUED)
    updated = Turn.objects.filter(pk=turn.pk, status__in=from_states).update(
        status=status, finished_at=now, result_note=result_note
    )
    turn.refresh_from_db()
    if not updated:
        return turn
    append_events(turn, [{"kind": "status", "payload": {"status": status, "result_note": result_note}}])
    return turn


# --------------------------------------------------------------------------------------
# AgentSchedule — recurring turns. The runner evaluates the cron and calls fire_schedule;
# the server materializes a normal Turn. See models.AgentSchedule.
# --------------------------------------------------------------------------------------

def _occurrences(schedule):
    """This schedule's turns — scheduled AND manual. Occurrence-based, not
    origin-based: a "Run now" turn is an attempt at the same work, so it must
    participate in latest/supersede/release exactly as a fired slot does."""
    return Turn.objects.filter(
        agent_id=schedule.agent_id, origin_ref__schedule_id=schedule.id
    )


def latest_occurrence_turn(schedule) -> Turn | None:
    """The newest turn this schedule produced — scheduled or manual run-now —
    whatever its status."""
    return _occurrences(schedule).order_by("-created_at").first()


def supersede_open_turns(schedule, *, reason: str) -> int:
    """Terminate this schedule's non-terminal turns as MISSED. Supersede and
    grace-release are the same operation at two timescales."""
    open_turns = _occurrences(schedule).filter(status__in=list(Turn.NON_TERMINAL))
    count = 0
    for turn in open_turns:
        finish_turn(turn, status=Turn.MISSED, result_note=reason, allow_queued=True)
        count += 1
    return count


def fire_schedule(schedule, slot: dt.datetime) -> tuple[Turn, bool]:
    """Materialize `slot` as a queued Turn. Supersedes any still-open occurrence
    of the same schedule first — you only ever owe the newest.

    Safe to call concurrently from both macOS-account runners: the slot-derived
    idempotency_key collapses the race inside enqueue_turn.
    """
    key = f"sched:{schedule.id}:{slot.isoformat()}"
    with transaction.atomic():
        if not Turn.objects.filter(idempotency_key=key).exists():
            supersede_open_turns(schedule, reason=f"superseded by slot {slot.isoformat()}")
        turn, created = enqueue_turn(
            agent=schedule.agent,
            origin=Turn.ORIGIN_CRON,
            idempotency_key=key,
            prompt=schedule.prompt,
            origin_ref={"schedule_id": schedule.id, "slot": slot.isoformat()},
            routing=schedule.routing,
        )
        if created and (schedule.last_slot is None or slot > schedule.last_slot):
            schedule.last_slot = slot
            schedule.save(update_fields=["last_slot", "updated_at"])
    return turn, created


def run_schedule_now(schedule) -> Turn:
    """Manual off-cycle trigger. Supersedes any still-open occurrence first,
    exactly as fire_schedule does — you only ever owe the newest, however it was
    launched. Run now is the designed remediation for an unfinished slot, so it
    must retire the slot it remediates; otherwise finishing the manual turn
    clears the nag (it is the newest occurrence) while the slot turn sits queued
    and still owed, and the work runs a second time when it is claimed later.

    origin=manual with a uuid-suffixed key, so an ad-hoc run never collides with
    a real slot, and last_slot is untouched — the CADENCE is unaffected (the next
    real slot still fires on time).
    """
    with transaction.atomic():
        supersede_open_turns(schedule, reason="superseded by a manual run")
        turn, _ = enqueue_turn(
            agent=schedule.agent,
            origin=Turn.ORIGIN_MANUAL,
            idempotency_key=f"sched:{schedule.id}:manual:{uuid.uuid4()}",
            prompt=schedule.prompt,
            origin_ref={"schedule_id": schedule.id, "manual": True},
            routing=schedule.routing,
        )
    return turn


def release_stale_occurrence_turns(schedule, *, now: dt.datetime | None = None) -> int:
    """Release this schedule's turns that have HELD the agent past grace_minutes.

    This is what keeps a forgotten session from wedging the agent: an executing
    turn holds one_executing_turn_per_agent, and the runner's heartbeat keeps
    renewing its lease for as long as the emdash session is open, so the ordinary
    lease sweep never rescues it.

    Scoped to EXECUTING (not NON_TERMINAL) and anchored on claimed_at (not
    created_at) because both are statements about *holding*, which is what
    grace_minutes bounds:
      - a QUEUED turn holds nothing (the index does not cover it), so releasing
        it could not unwedge anything — it would only destroy work still owed
        (laptop offline over a weekend must not retire Friday's slot). Retiring
        a stale queued occurrence is supersede_open_turns' job, at the right
        moment.
      - created_at measures *owed* time, so a turn queued longer than grace would
        be born past-grace and get aborted on its first sweep after being claimed
        — killing live human work in the function meant to protect it.
    claimed_at is non-null for every EXECUTING turn: claim_next_turn writes it,
    and claiming is the only route into those states.
    """
    now = now or timezone.now()
    cutoff = now - dt.timedelta(minutes=schedule.grace_minutes)
    stale = _occurrences(schedule).filter(status__in=EXECUTING, claimed_at__lt=cutoff)
    count = 0
    for turn in stale:
        finish_turn(
            turn, status=Turn.MISSED,
            result_note=f"released after {schedule.grace_minutes}m unattended",
        )
        count += 1
    return count


def release_stale_occurrence_turns_all(*, now: dt.datetime | None = None) -> int:
    """Fleet-wide release, run lazily on the claim tick (see claim_next_turn).

    Release belongs here, not on the fire tick: fire already supersedes
    everything release would touch, and a weekly schedule's fire tick is 10,080
    minutes apart — it could never honour a 120-minute grace between
    occurrences. On claim, a release unblocks the very same claim.

    The scan is a handful of rows: the executing-turn index caps this at ~one
    turn per agent.
    """
    now = now or timezone.now()
    schedule_ids = {
        turn.origin_ref.get("schedule_id")
        for turn in Turn.objects.filter(status__in=EXECUTING).only("origin_ref")
    }
    schedule_ids.discard(None)
    if not schedule_ids:
        return 0
    return sum(
        release_stale_occurrence_turns(schedule, now=now)
        for schedule in AgentSchedule.objects.filter(id__in=schedule_ids)
    )


# --------------------------------------------------------------------------------------
# SessionLink — durable thread↔session mapping (cross-account); see models.SessionLink
# --------------------------------------------------------------------------------------

def resolve_session(agent, thread_key: str, runner: Runner) -> dict:
    """Given (agent, thread_key) and the CURRENTLY-active runner, decide how to execute.

    Returns a plan dict:
      - reuse (bool): the live session hint is owned by THIS runner/host — the runner
        should verify the emdash task still exists and drive it (send prompt into it).
      - emdash_task_id: the task to reuse (only meaningful when reuse=True).
      - agent_task_ext_id / summary: durable context for rehydration when reuse=False
        (fresh session under this account) or for a brand-new thread.
      - link_id: the SessionLink id (None if no link exists yet — brand-new thread).

    Never assumes the live session is reachable: reuse is only proposed when the hint's
    runner + macOS host match the caller (the two-account failover invariant)."""
    link = SessionLink.objects.filter(agent=agent, thread_key=thread_key).first()
    if link is None:
        return {"reuse": False, "emdash_task_id": "", "agent_task_ext_id": "",
                "summary": "", "link_id": None, "new_thread": True}
    return {
        "reuse": link.reusable_by(runner),
        "emdash_task_id": link.live_emdash_task_id,
        "agent_task_ext_id": link.agent_task_ext_id,
        "summary": link.summary,
        "link_id": str(link.id),
        "new_thread": False,
    }


def record_session(
    agent,
    thread_key: str,
    *,
    runner: Runner,
    emdash_task_id: str = "",
    session_id: str = "",
    agent_task_ext_id: str | None = None,
    summary: str | None = None,
) -> SessionLink:
    """Upsert the durable link and re-point its live-session hint at THIS runner/host.

    Called after a session is created or reused so the next inbound event on the thread
    resolves to the right session (or, from the other account, knows to rehydrate). Only
    overwrites agent_task_ext_id/summary when a value is passed — otherwise preserves the
    durable context accumulated so far."""
    with transaction.atomic():
        link, _ = SessionLink.objects.select_for_update().get_or_create(
            agent=agent, thread_key=thread_key
        )
        link.live_runner = runner
        link.live_host = runner.host
        link.live_emdash_task_id = emdash_task_id
        link.live_session_id = session_id
        link.live_seen_at = timezone.now()
        if agent_task_ext_id is not None:
            link.agent_task_ext_id = agent_task_ext_id
        if summary is not None:
            link.summary = summary
        link.save()
    return link
