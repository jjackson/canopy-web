"""Harness domain services — the only write path for Runner/Turn/TurnEvent.

Claiming is a single conditional UPDATE (no row can be claimed twice); leases
are renewed by runner heartbeats and swept lazily on claim. All functions are
synchronous and transaction-safe.
"""
from __future__ import annotations

import datetime as dt
import logging

from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from .models import Runner, SessionLink, Turn, TurnEvent

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
    candidates = (
        Turn.objects.filter(status=Turn.QUEUED, agent__slug__in=slugs)
        .exclude(agent_id__in=busy_agents)
        .filter(routing_q)
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


def finish_turn(turn: Turn, *, status: str, result_note: str = "") -> Turn:
    """Transition CLAIMED|RUNNING|NEEDS_HUMAN -> DONE|FAILED. A no-op (no
    event, no field writes) if the turn is already terminal — idempotent, and
    guards against resurrecting a turn already swept to lost."""
    if status not in (Turn.DONE, Turn.FAILED):
        raise ValueError(f"finish status must be done|failed, got {status!r}")
    now = timezone.now()
    updated = Turn.objects.filter(
        pk=turn.pk, status__in=[Turn.CLAIMED, Turn.RUNNING, Turn.NEEDS_HUMAN]
    ).update(status=status, finished_at=now, result_note=result_note)
    turn.refresh_from_db()
    if not updated:
        return turn
    append_events(turn, [{"kind": "status", "payload": {"status": status, "result_note": result_note}}])
    return turn


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
