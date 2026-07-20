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

from apps.workspaces import services as wsvc

from .models import (
    AgentSchedule,
    Item,
    Runner,
    SessionLink,
    Turn,
    TurnEvent,
)

# HEARTBEAT_ONLINE_WINDOW lives on models.py (Runner.live_status uses it too;
# models.py cannot import services.py, which already imports models.py) and is
# re-exported here so existing importers of services.HEARTBEAT_ONLINE_WINDOW keep
# working. Intentional re-export — noqa keeps the F401 gate from deleting it.
from .models import HEARTBEAT_ONLINE_WINDOW  # noqa: F401

logger = logging.getLogger(__name__)

DEFAULT_LEASE_SECONDS = 900


def enqueue_turn(
    *,
    agent=None,
    project: str = "",
    session=None,
    workspace=None,
    origin: str,
    idempotency_key: str,
    prompt: str = "",
    origin_ref: dict | None = None,
    routing: str = Turn.PREFER_LOCAL,
    enqueued_by=None,
) -> tuple[Turn, bool]:
    """Queued turns stack freely — the executing-turn index never blocks intake
    (new turns are born `queued`, which the index does not cover).

    Targets exactly one of agent / project / session. A project turn must carry a
    workspace: it has no agent/session to derive tenancy from, and claim_next_turn
    fails it closed without one, so accepting it here would silently queue a turn
    nothing can ever run. Session turns derive tenancy from session.workspace.
    """
    if sum([bool(agent), bool(project), bool(session)]) != 1:
        raise ValueError("a turn targets exactly one of agent / project / session")
    if project and workspace is None:
        raise ValueError("a project turn needs a workspace")
    existing = Turn.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            turn = Turn.objects.create(
                agent=agent,
                project=project,
                chat_session=session,
                # Agent + session turns derive tenancy (agent.workspace /
                # chat_session.workspace) and must not denormalize a second copy
                # that can drift; only a project turn carries its own workspace FK.
                workspace=workspace if project else None,
                origin=origin,
                idempotency_key=idempotency_key,
                prompt=prompt,
                origin_ref=origin_ref or {},
                routing=routing,
                enqueued_by=enqueued_by if getattr(enqueued_by, "is_authenticated", False) else None,
            )
    except IntegrityError:
        # Only possible race: same idempotency key inserted concurrently.
        replay = Turn.objects.filter(idempotency_key=idempotency_key).first()
        if replay is not None:
            return replay, False
        raise
    return turn, True


def heartbeat(
    runner: Runner, *, active_turn_ids: list[str], degraded: bool = False, note: str = "",
    ready: bool = True, ready_note: str = "",
) -> Runner:
    now = timezone.now()
    runner.last_heartbeat_at = now
    runner.status = Runner.DEGRADED if degraded else Runner.ONLINE
    runner.status_note = note
    runner.ready = ready
    runner.ready_note = ready_note
    runner.save(update_fields=["last_heartbeat_at", "status", "status_note", "ready", "ready_note"])
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
    if runner.live_status != Runner.ONLINE:
        return None
    sweep_expired_leases()
    # Lazy sweeps, both BEFORE the busy_agents read: a turn released here frees
    # its agent for the very claim we are about to make.
    release_stale_occurrence_turns_all()
    slugs = runner.agent_slugs()
    projects = runner.project_names()
    if exclude_slugs:
        # Per-agent pause: the runner locally paused these agents; never claim their
        # queued turns (they stay QUEUED, resumed the moment the pause is lifted).
        # Scoped to agents by name and by nature — pausing an agent says nothing
        # about a repo, so project turns keep flowing.
        slugs = [s for s in slugs if s not in set(exclude_slugs)]
    if not slugs and not projects:
        return None
    routing_q = Q(routing__in=[Turn.PREFER_LOCAL, Turn.LOCAL_ONLY, Turn.ANY])
    if runner.kind == Runner.CLOUD:
        routing_q = Q(routing=Turn.ANY) | Q(routing=Turn.PREFER_LOCAL)
        # prefer_local turns fall to cloud only via the Phase 2 router policy;
        # Phase 0 has no cloud runners, so keep the simple rule: cloud never
        # takes local_only.
    busy_agents = Turn.objects.filter(status__in=EXECUTING).values("agent_id")
    # Tenant boundary. capabilities is a caller-supplied routing hint declared at
    # pairing and never validated (b4f5ead, Critical); the workspace is the actual
    # gate, and the two INTERSECT — one never substitutes for the other.
    #
    # The tenant derives from `paired_by` — the human who paired the runner — NOT
    # from the Runner.workspace FK. A runner.workspace is ONE workspace, while the
    # agent fleet deliberately spans several ("link each agent to its OWN
    # workspace (fleet spans workspaces)") behind a single laptop runner. Scoping
    # by the FK took production down: the sole runner was backfilled onto `dimagi`
    # while ace/ada/echo/hal live in `connect`, so 4 of 5 agents could not execute
    # any turn and their turns sat QUEUED indefinitely. This also makes the rule
    # agree with _runner_schedule_qs, which already derives tenancy this way.
    #
    # Still a real boundary, and the b4f5ead exploit stays closed: paired_by is
    # server-assigned from request.user at pairing, so unlike capabilities it is
    # not attacker-controlled. An outsider pairing a runner that declares a
    # victim's agent slug gets only THEIR OWN workspaces, so the victim's agent
    # stays unclaimable. Conversely a runner paired by someone who is a member of
    # a workspace may claim its agents' turns — that human can already drive those
    # agents through the UI, so there is no escalation.
    #
    # NULL paired_by fails closed for anything tenanted: no pairer means no
    # identity to derive a tenant from, so the slug set is empty and `__in=set()`
    # matches nothing (inferring a tenant from the FK would be an escalation — an
    # orphaned runner would keep claiming for a workspace whose owner is gone).
    #
    # The null-workspace leg stays: agents predating tenancy are ungated here
    # exactly as in list_turns / _runner_schedule_qs, and it is what the
    # pre-tenancy suite (runner + agent both null) runs on. Not a production hole
    # — agents/0007 backfilled every live agent onto a workspace.
    ws_slugs = wsvc.user_workspace_slugs(runner.paired_by) if runner.paired_by_id else set()
    # Project turns are gated on their OWN workspace FK and get NO null-workspace
    # escape hatch. The naive widening is a hole: a project turn has agent=NULL,
    # so `agent__workspace_id__isnull=True` — the leg that ungates pre-tenancy
    # AGENTS — matches every project turn, making them claimable by any runner in
    # any tenant. The two legs must therefore be split by target kind, and the
    # project leg fails closed on a NULL workspace.
    agent_tenant_q = Q(agent__workspace_id__in=ws_slugs) | Q(agent__workspace_id__isnull=True)
    tenant_q = (Q(agent__isnull=False) & agent_tenant_q) | (
        Q(agent__isnull=True) & Q(workspace_id__in=ws_slugs)
    )
    # `busy_agents` serializes AGENTS only, and a project turn (agent_id NULL)
    # must not be swept up by it. This plain exclude() is correct: Django compiles
    # it to `NOT (agent_id IN (…) AND agent_id IS NOT NULL)`, so NULL-agent rows
    # survive rather than falling into SQL's NULL-propagation trap. Verified by
    # test_a_busy_agent_does_not_block_a_project_turn, which is what makes it safe
    # to rely on.
    candidates = (
        Turn.objects.filter(status=Turn.QUEUED)
        .filter(Q(agent__slug__in=slugs) | Q(project__in=projects))
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

    # Fire AFTER commit so subscribers (apps/realtime) fan out durable rows and
    # never race the DB. Local import + on_commit avoids an import-time cycle and
    # a fan-out on a transaction that ultimately rolls back. bulk_create emits no
    # post_save, so this signal is the only hook a live tail can ride.
    def _fire_appended():
        from apps.harness.signals import turn_events_appended

        turn_events_appended.send(sender=Turn, turn=turn, rows=rows)

    transaction.on_commit(_fire_appended)
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

def _link_target(agent, project: str, workspace=None) -> dict:
    """Lookup kwargs for a link's target, enforcing the agent-XOR-project rule in
    Python as well as in the DB.

    Both agent/project keys are always present and one is always the empty/NULL
    sentinel. That is deliberate: `filter(agent=a)` alone would match a project row
    whose agent is NULL only by accident of the query, and `get_or_create(agent=
    None)` would otherwise omit `project` and create a row the CheckConstraint
    rejects.

    For a PROJECT, `workspace` is part of the IDENTITY, not just a stored field:
    it goes in the get_or_create/filter lookup so a link is scoped to the caller's
    tenant by construction. Without it, one runner's get_or_create on a guessed
    thread_key would FIND (and hijack) another tenant's link. With it, the guess
    lands in the guesser's own workspace and never touches the victim's row.
    """
    if bool(agent) == bool(project):
        raise ValueError("a session link targets an agent XOR a project")
    if agent:
        return {"agent": agent, "project": ""}
    if workspace is None:
        raise ValueError("a project session link needs a workspace")
    return {"agent": None, "project": project, "workspace": workspace}


def resolve_session(agent, thread_key: str, runner: Runner, *, project: str = "", workspace=None) -> dict:
    """Given (target, thread_key) and the CURRENTLY-active runner, decide how to execute.

    `agent` may be None when `project` is given — the phone addresses repos too.

    Returns a plan dict:
      - reuse (bool): the live session hint is owned by THIS runner/host — the runner
        should verify the emdash task still exists and drive it (send prompt into it).
      - emdash_task_id: the task to reuse (only meaningful when reuse=True).
      - agent_task_ext_id / summary: durable context for rehydration when reuse=False
        (fresh session under this account) or for a brand-new thread.
      - link_id: the SessionLink id (None if no link exists yet — brand-new thread).

    Never assumes the live session is reachable: reuse is only proposed when the hint's
    runner + macOS host match the caller (the two-account failover invariant)."""
    link = SessionLink.objects.filter(
        thread_key=thread_key, **_link_target(agent, project, workspace)
    ).first()
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


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    """Coerce a possibly-naive datetime to aware (UTC). The runner sends ISO8601
    (typically already UTC via a trailing "Z"), but a naive value would otherwise
    hit Django's USE_TZ=True as a silent local-time footgun rather than a clean
    UTC stamp."""
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, dt.timezone.utc)
    return value


def record_session(
    agent,
    thread_key: str,
    *,
    runner: Runner,
    project: str = "",
    workspace=None,
    emdash_task_id: str = "",
    session_id: str = "",
    agent_task_ext_id: str | None = None,
    summary: str | None = None,
) -> SessionLink:
    """Upsert the durable link and re-point its live-session hint at THIS runner/host.

    Called after a session is created or reused so the next inbound event on the thread
    resolves to the right session (or, from the other account, knows to rehydrate). Only
    overwrites agent_task_ext_id/summary when a value is passed — otherwise preserves the
    durable context accumulated so far.

    `workspace` stamps a PROJECT link's tenant (agent links derive it via the
    agent). The API caller must have already gated the runner's pairer against
    this workspace — the service stores, it does not authorize."""
    # workspace is part of a project link's identity (see _link_target), so it is
    # set by get_or_create's lookup — no separate assignment needed.
    with transaction.atomic():
        link, _ = SessionLink.objects.select_for_update().get_or_create(
            thread_key=thread_key, **_link_target(agent, project, workspace)
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


@transaction.atomic
def replace_reported_sessions(runner: Runner, workspace, sessions: list) -> int:
    """Wholesale-replace this runner's reported EmdashSessions, and upsert a
    SessionLink per session so `continue` rides the existing reuse path.

    Wholesale: a session that vanished from emdash simply stops being reported and
    disappears here. The SessionLinks are NOT deleted on drop — a durable link that
    revives when the session reappears is harmless, and deleting them would fight the
    reuse machinery; a stale link only ever resolves to reuse if its live hint still
    matches, which the next real report refreshes.
    """
    from .models import EmdashSession

    EmdashSession.objects.filter(runner=runner).delete()
    EmdashSession.objects.bulk_create([
        EmdashSession(
            runner=runner, workspace=workspace, emdash_task=s.emdash_task,
            project=s.project, status=s.status,
            last_interacted_at=_aware(s.last_interacted_at),
            recent_messages=list(s.recent_messages or []),
        )
        for s in sessions
    ])
    for s in sessions:
        if s.project:
            # live_session_id intentionally left blank here — a session report has
            # no session_id to give; reuse keys on live_emdash_task_id +
            # live_runner + live_host instead.
            record_session(
                None, f"emdash:{s.emdash_task}", runner=runner, project=s.project,
                workspace=workspace, emdash_task_id=s.emdash_task,
            )
    return len(sessions)


def list_visible_sessions(user) -> list:
    """Open sessions in the caller's workspaces whose runner is LIVE. Runner liveness
    (not deletion) is what suppresses a briefly-offline runner's stale rows — see
    Runner.live_status. Newest-first.

    auto_join_workspaces runs first, mirroring list_turns: this is a flat-path
    handler (GET /api/harness/sessions), so WorkspaceResolveMiddleware's
    tenant-prefix auto-join never fires for it. Without this call, a
    domain-matching teammate who hasn't hit any other endpoint yet has no
    WorkspaceMembership row and user_workspace_slugs(user) returns empty,
    silently hiding their workspace's sessions instead of listing them.
    """
    from .models import EmdashSession

    wsvc.auto_join_workspaces(user)
    ws_slugs = wsvc.user_workspace_slugs(user)
    rows = (
        EmdashSession.objects.filter(workspace_id__in=ws_slugs)
        .select_related("runner")
        .order_by("-last_interacted_at")
    )
    return [s for s in rows if s.runner.live_status == Runner.ONLINE]


# ---------------------------------------------------------------------------
# Items — the supervisor's queue (the dual of Turn)
# ---------------------------------------------------------------------------


class AlreadyDecidedError(Exception):
    """An item can be decided once. A second decision is a conflict (409), not a
    second dispatch."""


def create_items(*, agent, payloads: list[dict]) -> list[Item]:
    """Create items for an agent, idempotent per idempotency_key. A producer that
    re-posts its batch (a retried audit) gets the same rows back, not duplicates."""
    out: list[Item] = []
    for p in payloads:
        key = p["idempotency_key"]
        existing = Item.objects.filter(idempotency_key=key).first()
        if existing is not None:
            out.append(existing)
            continue
        try:
            with transaction.atomic():
                out.append(Item.objects.create(
                    agent=agent,
                    kind=p.get("kind") or Item.REVIEW,
                    title=p["title"],
                    body=p.get("body") or "",
                    origin=p.get("origin") or Turn.ORIGIN_API,
                    origin_ref=p.get("origin_ref") or {},
                    dispatch=p.get("dispatch") or [],
                    batch_key=p.get("batch_key") or "",
                    idempotency_key=key,
                    raised_by_id=p.get("raised_by") or None,
                ))
        except IntegrityError:
            replay = Item.objects.filter(idempotency_key=key).first()
            if replay is None:
                raise
            out.append(replay)
    return out


def decide_item(
    item: Item, *, decision: str, comment: str, by: str, actor_workspace_slugs: set[str],
    decided_by_user=None,
) -> tuple[Item, list[Turn]]:
    """Resolve an open item. Only IMPLEMENT dispatches.

    A review needs a decision from the closed set; a question needs a non-empty
    answer (its `decision` stays blank). Deciding twice raises AlreadyDecidedError —
    the guard that stops a double-click becoming a second dispatch.

    `actor_workspace_slugs` is the set of workspaces the DECIDING human belongs to;
    it's the authorization for a cross-agent dispatch — you may only dispatch a
    turn onto an agent in a workspace you're a member of (the hard tenant boundary).
    """
    from .dispatch import dispatch as dispatch_item  # local: dispatch imports services

    if item.state != Item.OPEN:
        raise AlreadyDecidedError(f"item {item.id} is already {item.state}")

    if item.kind == Item.QUESTION:
        if not (comment or "").strip():
            raise ValueError("a question is resolved by its answer — comment must not be empty")
        decision = ""
    elif decision not in (Item.IMPLEMENT, Item.SKIP, Item.DEFER):
        raise ValueError(
            f"decision must be one of implement|skip|defer, got {decision!r}"
        )

    # ATOMIC, and this is the whole ballgame. dispatch() raises on a bad spec
    # (unknown target_agent). Committing the decision first would leave the item
    # DECIDED but undispatched — and since deciding twice is a 409, permanently
    # unfixable: the work silently never happens while the UI says you approved it.
    # Rolling back instead means a bad spec is a 422 on an item that is still OPEN,
    # retryable the moment the producer fixes it.
    with transaction.atomic():
        item.state = Item.DECIDED
        item.decision = decision
        item.comment = comment or ""
        item.decided_by = by
        item.decided_by_user = decided_by_user if getattr(decided_by_user, "is_authenticated", False) else None
        item.decided_at = timezone.now()

        turns: list[Turn] = []
        if decision == Item.IMPLEMENT:
            turns = dispatch_item(item, actor_workspace_slugs=actor_workspace_slugs)
            item.dispatched_at = timezone.now()

        item.save(update_fields=[
            "state", "decision", "comment", "decided_by", "decided_by_user",
            "decided_at", "dispatched_at",
        ])
    return item, turns


def dismiss_item(item: Item, *, by: str, decided_by_user=None) -> Item:
    """Retire an OPEN item without acting — a producer that raised it in error, or
    a subject that changed under it.

    Only an OPEN item may be dismissed. Dismissing an already-DECIDED item would
    overwrite `decided_by`/`decided_at` — erasing who approved it — while the turns
    that decision already dispatched keep running: the queue would read "dismissed"
    for work that is executing, with the approver's identity gone. So dismiss guards
    on state exactly like decide does; a re-dismiss is likewise a 409, not a
    silent second write."""
    if item.state != Item.OPEN:
        raise AlreadyDecidedError(f"item {item.id} is already {item.state}")
    item.state = Item.DISMISSED
    item.decided_by = by
    item.decided_by_user = decided_by_user if getattr(decided_by_user, "is_authenticated", False) else None
    item.decided_at = timezone.now()
    item.save(update_fields=["state", "decided_by", "decided_by_user", "decided_at"])
    return item
