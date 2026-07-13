# Agent Execution Phase 0 — Laptop Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A board command in canopy-web becomes a visible interactive claude session in emdash on Jonathan's laptop within ~2 minutes, deterministically, with turn state tracked in Postgres.

**Architecture:** New framework-tier Django app `apps/harness` (Runner/Turn/TurnEvent + atomic claim/lease API mounted at `/api/harness/`), a stdlib-only Python runner package `packages/canopy_runner` that heartbeats, claims turns, and triggers emdash by inserting a `queued` row into emdash's `automation_runs` SQLite table (mechanism proven by live experiment 2026-07-05), and a `drain-turn` skill in the canopy plugin that the spawned session runs to do the work and close the turn.

**Tech Stack:** Django 5 + Django Ninja 1.x + Pydantic v2 (existing patterns), pytest-django, Python 3.12 stdlib only for the runner (sqlite3/urllib/json), launchd for the laptop daemon.

**Spec:** `docs/superpowers/specs/2026-07-05-agent-execution-control-plane-design.md`

## Global Constraints

- **Naming deviation from spec (locked here):** the app is `apps/harness`, NOT `apps/sessions` — `django.contrib.sessions` owns the `sessions` app label and `/api/sessions` is already session_sharing's mount. Task 1 records this in the spec.
- `apps/harness` is FRAMEWORK tier: it may import `agents`, `workspaces`, `tokens`, `common`, `api` — never product apps (`projects`, `walkthroughs`, `reviews`, `shareouts`, `runs`). `tests/test_architecture_boundary.py` enforces.
- All request/response bodies are Pydantic v2 models in `apps/harness/schemas.py`; routes in `apps/harness/api.py` on a `Router(auth=session_auth)`; errors RFC 7807 via existing `ProblemError`.
- Every side-effecting create endpoint takes an idempotency key.
- Runner package: Python 3.12 stdlib only (no requests/httpx). It must never write to emdash's DB when the schema version check fails.
- Turn lifecycle strings (exact): `queued`, `claimed`, `running`, `needs_human`, `done`, `failed`, `lost`. Runner kinds: `emdash`, `cloud`, `remote`. Runner statuses: `online`, `stale`, `disconnected`, `degraded`, `retired`.
- Lease TTL default 15 minutes; heartbeat interval 30s; runner work-poll interval 20s; `online` = heartbeat within 90s.
- At most one non-terminal Turn per agent (partial unique index).
- Commit after every task (git, this repo unless a task says otherwise).

---

### Task 1: Record the naming decision in the spec

**Files:**
- Modify: `docs/superpowers/specs/2026-07-05-agent-execution-control-plane-design.md` (§5 heading area)

**Interfaces:**
- Produces: spec text matching what Tasks 2+ build (`apps/harness`, `/api/harness/`).

- [ ] **Step 1: Edit the spec.** Replace the §5 heading line:

```
## 5. Control plane (`apps/sessions`, framework tier)
```

with:

```
## 5. Control plane (`apps/harness`, framework tier)

> **Naming note (2026-07-05):** implementation uses `apps/harness` mounted at
> `/api/harness/` — `django.contrib.sessions` owns the `sessions` app label and
> `/api/sessions` is already the session_sharing mount. "Live-session harness"
> intent unchanged.
```

Also replace the two other occurrences of `apps/sessions` (§5.1 intro sentence, §5.3 heading `mounted at /api/sessions/`, §7 module mentions `slack.py module inside apps/sessions`) with `apps/harness` / `/api/harness/`.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-07-05-agent-execution-control-plane-design.md
git commit -m "spec: control-plane app is apps/harness (sessions label/mount collision)"
```

---

### Task 2: `apps/harness` app scaffold + models

**Files:**
- Create: `apps/harness/__init__.py`, `apps/harness/apps.py`, `apps/harness/models.py`, `apps/harness/admin.py`, `apps/harness/migrations/__init__.py`
- Modify: `config/settings/base.py` (INSTALLED_APPS), `tests/test_architecture_boundary.py:27` (FRAMEWORK set)
- Test: `tests/test_harness_models.py`

**Interfaces:**
- Produces: models `Runner`, `Turn`, `TurnEvent` with fields/choices exactly as below; later tasks import `from apps.harness.models import Runner, Turn, TurnEvent`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_models.py
"""Model-level invariants for the agent-execution harness."""
from __future__ import annotations

import pytest
from django.db import IntegrityError

from apps.agents.models import Agent
from apps.harness.models import Runner, Turn, TurnEvent

pytestmark = pytest.mark.django_db


def _agent(slug="echo"):
    return Agent.objects.create(slug=slug, name=slug.title())


def _runner(**kw):
    defaults = dict(name="jj-mbp", kind=Runner.EMDASH, capabilities={"agents": ["echo"]})
    defaults.update(kw)
    return Runner.objects.create(**defaults)


def test_turn_defaults_to_queued():
    t = Turn.objects.create(agent=_agent(), origin=Turn.ORIGIN_BOARD, idempotency_key="k1")
    assert t.status == Turn.QUEUED
    assert t.routing == Turn.PREFER_LOCAL


def test_one_non_terminal_turn_per_agent():
    a = _agent()
    Turn.objects.create(agent=a, origin=Turn.ORIGIN_BOARD, idempotency_key="k1")
    with pytest.raises(IntegrityError):
        Turn.objects.create(agent=a, origin=Turn.ORIGIN_BOARD, idempotency_key="k2")


def test_terminal_turn_frees_the_lane():
    a = _agent()
    t = Turn.objects.create(agent=a, origin=Turn.ORIGIN_BOARD, idempotency_key="k1")
    t.status = Turn.DONE
    t.save()
    Turn.objects.create(agent=a, origin=Turn.ORIGIN_BOARD, idempotency_key="k2")  # no raise


def test_idempotency_key_unique():
    a = _agent()
    t = Turn.objects.create(agent=a, origin=Turn.ORIGIN_BOARD, idempotency_key="k1")
    t.status = Turn.DONE
    t.save()
    with pytest.raises(IntegrityError):
        Turn.objects.create(agent=a, origin=Turn.ORIGIN_BOARD, idempotency_key="k1")


def test_turn_event_seq_unique_per_turn():
    t = Turn.objects.create(agent=_agent(), origin=Turn.ORIGIN_BOARD, idempotency_key="k1")
    TurnEvent.objects.create(turn=t, seq=1, kind="status", payload={"s": "claimed"})
    with pytest.raises(IntegrityError):
        TurnEvent.objects.create(turn=t, seq=1, kind="status", payload={})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harness_models.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'apps.harness'`

- [ ] **Step 3: Create the app**

```python
# apps/harness/__init__.py
```

```python
# apps/harness/apps.py
from django.apps import AppConfig


class HarnessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.harness"
    verbose_name = "Agent execution harness"
```

```python
# apps/harness/models.py
"""Agent-execution harness: runner registry, turns, and the turn-event ledger.

Framework tier. A Turn is the execution envelope for one unit of agent work;
Runners are executors that dial out (heartbeat + claim); TurnEvents are the
append-only ledger. See docs/superpowers/specs/2026-07-05-agent-execution-
control-plane-design.md.
"""
from __future__ import annotations

import uuid

from django.db import models


class Runner(models.Model):
    """A paired executor (laptop emdash daemon, cloud container, remote box)."""

    EMDASH, CLOUD, REMOTE = "emdash", "cloud", "remote"
    KIND_CHOICES = [(EMDASH, "Emdash"), (CLOUD, "Cloud"), (REMOTE, "Remote")]

    ONLINE, STALE, DISCONNECTED, DEGRADED, RETIRED = (
        "online", "stale", "disconnected", "degraded", "retired",
    )
    STATUS_CHOICES = [
        (ONLINE, "Online"), (STALE, "Stale"), (DISCONNECTED, "Disconnected"),
        (DEGRADED, "Degraded"), (RETIRED, "Retired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    capabilities = models.JSONField(default=dict, help_text='e.g. {"agents": ["echo"]}')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=DISCONNECTED)
    status_note = models.CharField(max_length=255, blank=True, default="")
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    paired_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    paired_at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["kind", "status"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"runner:{self.name}:{self.kind}:{self.status}"

    def agent_slugs(self) -> list[str]:
        return list(self.capabilities.get("agents", []))


class Turn(models.Model):
    """One unit of agent work — the execution envelope around board commands."""

    QUEUED, CLAIMED, RUNNING, NEEDS_HUMAN = "queued", "claimed", "running", "needs_human"
    DONE, FAILED, LOST = "done", "failed", "lost"
    STATUS_CHOICES = [
        (QUEUED, "Queued"), (CLAIMED, "Claimed"), (RUNNING, "Running"),
        (NEEDS_HUMAN, "Needs human"), (DONE, "Done"), (FAILED, "Failed"), (LOST, "Lost"),
    ]
    TERMINAL = {DONE, FAILED, LOST}
    NON_TERMINAL = {QUEUED, CLAIMED, RUNNING, NEEDS_HUMAN}

    ORIGIN_BOARD, ORIGIN_API, ORIGIN_SLACK, ORIGIN_CRON, ORIGIN_MANUAL = (
        "board", "api", "slack", "cron", "manual",
    )
    ORIGIN_CHOICES = [
        (ORIGIN_BOARD, "Board"), (ORIGIN_API, "API"), (ORIGIN_SLACK, "Slack"),
        (ORIGIN_CRON, "Cron"), (ORIGIN_MANUAL, "Manual"),
    ]

    PREFER_LOCAL, LOCAL_ONLY, ANY = "prefer_local", "local_only", "any"
    ROUTING_CHOICES = [(PREFER_LOCAL, "Prefer local"), (LOCAL_ONLY, "Local only"), (ANY, "Any")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey("agents.Agent", on_delete=models.CASCADE, related_name="turns")
    origin = models.CharField(max_length=10, choices=ORIGIN_CHOICES)
    origin_ref = models.JSONField(default=dict, blank=True)
    prompt = models.TextField(blank=True, default="")
    routing = models.CharField(max_length=15, choices=ROUTING_CHOICES, default=PREFER_LOCAL)
    idempotency_key = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=QUEUED)
    claimed_by = models.ForeignKey(
        Runner, on_delete=models.SET_NULL, null=True, blank=True, related_name="turns"
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    session_id = models.CharField(max_length=64, blank=True, default="")
    result_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["agent", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["agent"],
                condition=models.Q(status__in=["queued", "claimed", "running", "needs_human"]),
                name="one_active_turn_per_agent",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"turn:{self.agent.slug}:{self.status}:{self.id.hex[:8]}"


class TurnEvent(models.Model):
    """Append-only per-turn ledger. seq is monotonic per turn (assigned in services)."""

    turn = models.ForeignKey(Turn, on_delete=models.CASCADE, related_name="events")
    seq = models.PositiveIntegerField()
    ts = models.DateTimeField(auto_now_add=True)
    kind = models.CharField(max_length=20)  # status|assistant|tool_start|tool_end|question|error|heartbeat
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["seq"]
        constraints = [
            models.UniqueConstraint(fields=["turn", "seq"], name="turnevent_seq_unique_per_turn")
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"evt:{self.turn_id}:{self.seq}:{self.kind}"
```

```python
# apps/harness/admin.py
from django.contrib import admin

from .models import Runner, Turn, TurnEvent


@admin.register(Runner)
class RunnerAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "status", "last_heartbeat_at", "paired_at")
    list_filter = ("kind", "status")


@admin.register(Turn)
class TurnAdmin(admin.ModelAdmin):
    list_display = ("id", "agent", "origin", "status", "claimed_by", "created_at", "finished_at")
    list_filter = ("status", "origin")
    search_fields = ("id", "agent__slug")


@admin.register(TurnEvent)
class TurnEventAdmin(admin.ModelAdmin):
    list_display = ("turn", "seq", "kind", "ts")
    list_filter = ("kind",)
```

- [ ] **Step 4: Register the app + boundary tier.** In `config/settings/base.py`, add to `INSTALLED_APPS` next to the other `apps.*` entries:

```python
    "apps.harness",
```

In `tests/test_architecture_boundary.py:27`, add `"harness"` to the `FRAMEWORK` set:

```python
FRAMEWORK = {"agents", "agent_runs", "workspaces", "api", "common", "timeline", "tokens", "session_sharing", "issues", "mcp", "system", "harness"}
```

- [ ] **Step 5: Make migrations**

Run: `uv run python manage.py makemigrations harness`
Expected: `apps/harness/migrations/0001_initial.py` created with the three models + constraints.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_harness_models.py tests/test_architecture_boundary.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add apps/harness config/settings/base.py tests/test_harness_models.py tests/test_architecture_boundary.py
git commit -m "feat(harness): Runner/Turn/TurnEvent models with one-active-turn lane constraint"
```

---

### Task 3: Services — enqueue, heartbeat, claim, events, finish, lease sweep

**Files:**
- Create: `apps/harness/services.py`
- Test: `tests/test_harness_services.py`

**Interfaces:**
- Consumes: Task 2 models.
- Produces (exact signatures; Task 4 API calls these):
  - `enqueue_turn(*, agent, origin: str, idempotency_key: str, prompt: str = "", origin_ref: dict | None = None, routing: str = "prefer_local") -> tuple[Turn, bool]` — `(turn, created)`; replays existing turn on duplicate key; raises `LaneBusy` if the agent already has a non-terminal turn with a different key.
  - `heartbeat(runner: Runner, *, active_turn_ids: list[str], degraded: bool = False, note: str = "") -> Runner` — stamps `last_heartbeat_at`, sets status, renews leases for listed turns.
  - `claim_next_turn(runner: Runner, *, lease_seconds: int = 900) -> Turn | None` — atomic; sweeps expired leases first; respects routing/kind and runner capabilities.
  - `append_events(turn: Turn, events: list[dict]) -> int` — assigns `seq` after the current max; each dict has `kind` + `payload`; returns count.
  - `mark_running(turn: Turn, *, session_id: str = "") -> Turn`
  - `finish_turn(turn: Turn, *, status: str, result_note: str = "") -> Turn` — status must be `done` or `failed`.
  - `sweep_expired_leases() -> int` — non-terminal claimed/running turns past lease → `lost` (+ `status` event); returns count.
  - `class LaneBusy(Exception)`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_harness_services.py
"""Claim/lease/idempotency semantics for the harness services."""
from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.agents.models import Agent
from apps.harness import services
from apps.harness.models import Runner, Turn, TurnEvent

pytestmark = pytest.mark.django_db


def _agent(slug="echo"):
    return Agent.objects.create(slug=slug, name=slug.title())


def _runner(**kw):
    defaults = dict(name="jj-mbp", kind=Runner.EMDASH, capabilities={"agents": ["echo"]})
    defaults.update(kw)
    r = Runner.objects.create(**defaults)
    services.heartbeat(r, active_turn_ids=[])
    return r


def test_enqueue_is_idempotent():
    a = _agent()
    t1, created1 = services.enqueue_turn(agent=a, origin="board", idempotency_key="k1")
    t2, created2 = services.enqueue_turn(agent=a, origin="board", idempotency_key="k1")
    assert created1 is True and created2 is False and t1.pk == t2.pk


def test_enqueue_second_key_while_lane_busy_raises():
    a = _agent()
    services.enqueue_turn(agent=a, origin="board", idempotency_key="k1")
    with pytest.raises(services.LaneBusy):
        services.enqueue_turn(agent=a, origin="board", idempotency_key="k2")


def test_claim_next_turn_happy_path():
    a = _agent()
    t, _ = services.enqueue_turn(agent=a, origin="board", idempotency_key="k1")
    r = _runner()
    claimed = services.claim_next_turn(r)
    assert claimed.pk == t.pk
    claimed.refresh_from_db()
    assert claimed.status == Turn.CLAIMED
    assert claimed.claimed_by_id == r.id
    assert claimed.lease_expires_at > timezone.now()


def test_claim_respects_capabilities():
    a = _agent("eva")
    services.enqueue_turn(agent=a, origin="board", idempotency_key="k1")
    r = _runner()  # only capable of echo
    assert services.claim_next_turn(r) is None


def test_local_only_never_claimed_by_cloud():
    a = _agent()
    services.enqueue_turn(agent=a, origin="board", idempotency_key="k1", routing="local_only")
    r = _runner(kind=Runner.CLOUD)
    assert services.claim_next_turn(r) is None


def test_claim_is_exclusive():
    a = _agent()
    services.enqueue_turn(agent=a, origin="board", idempotency_key="k1")
    r1, r2 = _runner(), _runner(name="jj-mbp-2")
    first = services.claim_next_turn(r1)
    second = services.claim_next_turn(r2)
    assert first is not None and second is None


def test_expired_lease_goes_lost_and_is_reclaimable():
    a = _agent()
    services.enqueue_turn(agent=a, origin="board", idempotency_key="k1")
    r = _runner()
    t = services.claim_next_turn(r)
    Turn.objects.filter(pk=t.pk).update(lease_expires_at=timezone.now() - dt.timedelta(minutes=1))
    assert services.sweep_expired_leases() == 1
    t.refresh_from_db()
    assert t.status == Turn.LOST
    # lost is terminal -> lane free -> a re-enqueue with a new key claims fine
    services.enqueue_turn(agent=a, origin="board", idempotency_key="k2")
    assert services.claim_next_turn(r) is not None


def test_heartbeat_renews_lease_and_status():
    a = _agent()
    services.enqueue_turn(agent=a, origin="board", idempotency_key="k1")
    r = _runner()
    t = services.claim_next_turn(r)
    old_expiry = t.lease_expires_at
    services.heartbeat(r, active_turn_ids=[str(t.pk)])
    t.refresh_from_db()
    assert t.lease_expires_at > old_expiry
    r.refresh_from_db()
    assert r.status == Runner.ONLINE


def test_degraded_runner_claims_nothing():
    a = _agent()
    services.enqueue_turn(agent=a, origin="board", idempotency_key="k1")
    r = _runner()
    services.heartbeat(r, active_turn_ids=[], degraded=True, note="emdash schema drift")
    assert services.claim_next_turn(r) is None


def test_append_events_assigns_monotonic_seq():
    a = _agent()
    t, _ = services.enqueue_turn(agent=a, origin="board", idempotency_key="k1")
    n = services.append_events(t, [{"kind": "status", "payload": {"s": "claimed"}}])
    n += services.append_events(t, [{"kind": "status", "payload": {"s": "running"}}])
    assert n == 2
    assert list(t.events.values_list("seq", flat=True)) == [1, 2]


def test_finish_turn_sets_terminal_state():
    a = _agent()
    t, _ = services.enqueue_turn(agent=a, origin="board", idempotency_key="k1")
    services.finish_turn(t, status="done", result_note="2 commands applied")
    t.refresh_from_db()
    assert t.status == Turn.DONE and t.finished_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_harness_services.py -v`
Expected: FAIL with `AttributeError`/`ImportError` (no `apps.harness.services`)

- [ ] **Step 3: Implement services**

```python
# apps/harness/services.py
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

from .models import Runner, Turn, TurnEvent

logger = logging.getLogger(__name__)

DEFAULT_LEASE_SECONDS = 900
HEARTBEAT_ONLINE_WINDOW = dt.timedelta(seconds=90)


class LaneBusy(Exception):
    """The agent already has a non-terminal turn (different idempotency key)."""


def enqueue_turn(
    *,
    agent,
    origin: str,
    idempotency_key: str,
    prompt: str = "",
    origin_ref: dict | None = None,
    routing: str = Turn.PREFER_LOCAL,
) -> tuple[Turn, bool]:
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
    except IntegrityError as exc:
        # Either the lane constraint or a key race; disambiguate.
        replay = Turn.objects.filter(idempotency_key=idempotency_key).first()
        if replay is not None:
            return replay, False
        raise LaneBusy(f"agent '{agent.slug}' already has an active turn") from exc
    append_events(turn, [{"kind": "status", "payload": {"status": Turn.QUEUED}}])
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


def claim_next_turn(runner: Runner, *, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> Turn | None:
    if runner.status != Runner.ONLINE:
        return None
    sweep_expired_leases()
    slugs = runner.agent_slugs()
    if not slugs:
        return None
    routing_q = Q(routing__in=[Turn.PREFER_LOCAL, Turn.LOCAL_ONLY, Turn.ANY])
    if runner.kind == Runner.CLOUD:
        routing_q = Q(routing=Turn.ANY) | Q(routing=Turn.PREFER_LOCAL)
        # prefer_local turns fall to cloud only via the Phase 2 router policy;
        # Phase 0 has no cloud runners, so keep the simple rule: cloud never
        # takes local_only.
    candidates = Turn.objects.filter(
        status=Turn.QUEUED, agent__slug__in=slugs
    ).filter(routing_q).order_by("created_at")
    now = timezone.now()
    for turn in candidates:
        if not _kind_allows(runner, turn.routing):
            continue
        updated = Turn.objects.filter(pk=turn.pk, status=Turn.QUEUED).update(
            status=Turn.CLAIMED,
            claimed_by=runner,
            claimed_at=now,
            lease_expires_at=now + dt.timedelta(seconds=lease_seconds),
        )
        if updated:
            turn.refresh_from_db()
            append_events(turn, [{"kind": "status", "payload": {"status": Turn.CLAIMED, "runner": runner.name}}])
            return turn
    return None


def append_events(turn: Turn, events: list[dict]) -> int:
    with transaction.atomic():
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
    turn.status = Turn.RUNNING
    turn.started_at = turn.started_at or timezone.now()
    if session_id:
        turn.session_id = session_id
    turn.save(update_fields=["status", "started_at", "session_id"])
    append_events(turn, [{"kind": "status", "payload": {"status": Turn.RUNNING}}])
    return turn


def finish_turn(turn: Turn, *, status: str, result_note: str = "") -> Turn:
    assert status in (Turn.DONE, Turn.FAILED), f"finish status must be done|failed, got {status}"
    turn.status = status
    turn.finished_at = timezone.now()
    turn.result_note = result_note
    turn.save(update_fields=["status", "finished_at", "result_note"])
    append_events(turn, [{"kind": "status", "payload": {"status": status, "result_note": result_note}}])
    return turn
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_harness_services.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add apps/harness/services.py tests/test_harness_services.py
git commit -m "feat(harness): enqueue/heartbeat/claim/lease/event services with atomic claim"
```

---

### Task 4: Schemas + API router mounted at `/api/harness/`

**Files:**
- Create: `apps/harness/schemas.py`, `apps/harness/api.py`
- Modify: `apps/api/api.py` (import + `api.add_router("/harness", harness_router)` next to the other registrations at lines ~153-173)
- Test: `tests/test_harness_api.py`

**Interfaces:**
- Consumes: Task 3 services (exact signatures above).
- Produces endpoints (all under `/api/harness/`, session/PAT auth via existing `session_auth`):
  - `POST /runners/` body `{name, kind, capabilities}` → 201 RunnerOut (id used by the runner config)
  - `POST /runners/{id}/heartbeat` body `{active_turn_ids: [str], degraded: bool, note: str}` → RunnerOut
  - `POST /runners/{id}/claim` → 200 TurnOut or 204 (no work)
  - `POST /turns/` body `{agent_slug, origin, idempotency_key, prompt?, origin_ref?, routing?}` → 200/201 TurnOut (`created` flag), 409 problem+json when lane busy
  - `GET /turns/?agent=<slug>&status=<s>` → paginated TurnOut list
  - `GET /turns/{id}` → TurnOut
  - `POST /turns/{id}/events` body `{events: [{kind, payload}]}` → `{count}`
  - `GET /turns/{id}/events?after=<seq>` → `{events: [TurnEventOut]}`
  - `POST /turns/{id}/start` body `{session_id?}` → TurnOut
  - `POST /turns/{id}/finish` body `{status: "done"|"failed", result_note?}` → TurnOut

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_harness_api.py
"""API-level tests for /api/harness (runner pairing, claim loop, turn lifecycle)."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.agents.models import Agent
from apps.harness.models import Runner, Turn

pytestmark = pytest.mark.django_db


@pytest.fixture()
def client():
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture()
def agent():
    return Agent.objects.create(slug="echo", name="Echo")


def _pair(client) -> str:
    resp = client.post(
        "/api/harness/runners/",
        {"name": "jj-mbp", "kind": "emdash", "capabilities": {"agents": ["echo"]}},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()["id"]


def _hb(client, rid, active=None, degraded=False):
    return client.post(
        f"/api/harness/runners/{rid}/heartbeat",
        {"active_turn_ids": active or [], "degraded": degraded, "note": ""},
        content_type="application/json",
    )


def test_pair_heartbeat_claim_cycle(client, agent):
    rid = _pair(client)
    assert _hb(client, rid).status_code == 200

    enq = client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    )
    assert enq.status_code == 201

    claim = client.post(f"/api/harness/runners/{rid}/claim")
    assert claim.status_code == 200
    turn = claim.json()
    assert turn["status"] == "claimed" and turn["agent_slug"] == "echo"

    again = client.post(f"/api/harness/runners/{rid}/claim")
    assert again.status_code == 204


def test_enqueue_replays_on_same_key(client, agent):
    body = {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"}
    first = client.post("/api/harness/turns/", body, content_type="application/json")
    second = client.post("/api/harness/turns/", body, content_type="application/json")
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_enqueue_lane_busy_is_409(client, agent):
    client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    )
    resp = client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k2"},
        content_type="application/json",
    )
    assert resp.status_code == 409
    assert resp["Content-Type"] == "application/problem+json"


def test_event_append_and_cursor_read(client, agent):
    enq = client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    ).json()
    tid = enq["id"]
    resp = client.post(
        f"/api/harness/turns/{tid}/events",
        {"events": [{"kind": "status", "payload": {"s": "x"}}, {"kind": "assistant", "payload": {"text": "hi"}}]},
        content_type="application/json",
    )
    assert resp.status_code == 200 and resp.json()["count"] == 2
    # enqueue itself wrote seq 1 ("queued"); our two are 2 and 3
    events = client.get(f"/api/harness/turns/{tid}/events?after=1").json()["events"]
    assert [e["seq"] for e in events] == [2, 3]


def test_start_and_finish(client, agent):
    tid = client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    ).json()["id"]
    started = client.post(
        f"/api/harness/turns/{tid}/start", {"session_id": "abc"}, content_type="application/json"
    )
    assert started.status_code == 200 and started.json()["status"] == "running"
    finished = client.post(
        f"/api/harness/turns/{tid}/finish",
        {"status": "done", "result_note": "2 applied"},
        content_type="application/json",
    )
    assert finished.status_code == 200 and finished.json()["status"] == "done"


def test_list_filter_by_agent_and_status(client, agent):
    # the exact query the drain-turn skill issues
    client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    )
    resp = client.get("/api/harness/turns/?agent=echo&status=claimed,running,queued")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1 and body[0]["agent_slug"] == "echo"
    empty = client.get("/api/harness/turns/?agent=echo&status=done")
    assert empty.status_code == 200 and empty.json() == []


def test_anonymous_is_401(agent):
    c = Client()
    resp = c.get("/api/harness/turns/")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_harness_api.py -v`
Expected: FAIL (404s — router not mounted / modules missing)

- [ ] **Step 3: Implement schemas**

```python
# apps/harness/schemas.py
"""Pydantic schemas for the /api/harness surface."""
from __future__ import annotations

import datetime as dt
import uuid

from ninja import Schema


class RunnerIn(Schema):
    name: str
    kind: str  # emdash|cloud|remote
    capabilities: dict = {}


class RunnerOut(Schema):
    id: uuid.UUID
    name: str
    kind: str
    status: str
    status_note: str
    last_heartbeat_at: dt.datetime | None
    capabilities: dict


class HeartbeatIn(Schema):
    active_turn_ids: list[str] = []
    degraded: bool = False
    note: str = ""


class TurnIn(Schema):
    agent_slug: str
    origin: str
    idempotency_key: str
    prompt: str = ""
    origin_ref: dict = {}
    routing: str = "prefer_local"


class TurnOut(Schema):
    id: uuid.UUID
    agent_slug: str
    origin: str
    status: str
    routing: str
    prompt: str
    origin_ref: dict
    claimed_by_name: str | None
    session_id: str
    result_note: str
    created_at: dt.datetime
    claimed_at: dt.datetime | None
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    lease_expires_at: dt.datetime | None

    @staticmethod
    def resolve_agent_slug(obj) -> str:
        return obj.agent.slug

    @staticmethod
    def resolve_claimed_by_name(obj) -> str | None:
        return obj.claimed_by.name if obj.claimed_by else None


class TurnEventIn(Schema):
    kind: str
    payload: dict = {}


class TurnEventsIn(Schema):
    events: list[TurnEventIn]


class TurnEventOut(Schema):
    seq: int
    ts: dt.datetime
    kind: str
    payload: dict


class TurnEventsOut(Schema):
    events: list[TurnEventOut]


class CountOut(Schema):
    count: int


class TurnStartIn(Schema):
    session_id: str = ""


class TurnFinishIn(Schema):
    status: str  # done|failed
    result_note: str = ""
```

- [ ] **Step 4: Implement the router**

```python
# apps/harness/api.py
"""Django Ninja router for /api/harness — runner registry + turn lifecycle."""
from __future__ import annotations

from django.http import HttpRequest
from ninja import Router
from ninja.errors import HttpError

from apps.agents.models import Agent
from apps.api.auth import session_auth
from apps.api.errors import ProblemError

from . import services
from .models import Runner, Turn
from .schemas import (
    CountOut,
    HeartbeatIn,
    RunnerIn,
    RunnerOut,
    TurnEventsIn,
    TurnEventsOut,
    TurnFinishIn,
    TurnIn,
    TurnOut,
    TurnStartIn,
)

router = Router(auth=session_auth, tags=["harness"])


def _runner_or_404(runner_id) -> Runner:
    runner = Runner.objects.filter(pk=runner_id).exclude(status=Runner.RETIRED).first()
    if runner is None:
        raise HttpError(404, "runner not found")
    return runner


def _turn_or_404(turn_id) -> Turn:
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
        paired_by=request.user,
    )
    return 201, runner


@router.post("/runners/{runner_id}/heartbeat", response=RunnerOut)
def runner_heartbeat(request: HttpRequest, runner_id: str, payload: HeartbeatIn):
    runner = _runner_or_404(runner_id)
    return services.heartbeat(
        runner,
        active_turn_ids=payload.active_turn_ids,
        degraded=payload.degraded,
        note=payload.note,
    )


@router.post("/runners/{runner_id}/claim", response={200: TurnOut, 204: None})
def claim_turn(request: HttpRequest, runner_id: str):
    runner = _runner_or_404(runner_id)
    turn = services.claim_next_turn(runner)
    if turn is None:
        return 204, None
    return 200, turn


@router.post("/turns/", response={200: TurnOut, 201: TurnOut})
def enqueue_turn(request: HttpRequest, payload: TurnIn):
    agent = Agent.objects.filter(slug=payload.agent_slug).first()
    if agent is None:
        raise HttpError(404, f"agent '{payload.agent_slug}' not found")
    if payload.origin not in dict(Turn.ORIGIN_CHOICES):
        raise HttpError(422, f"unknown origin '{payload.origin}'")
    if payload.routing not in dict(Turn.ROUTING_CHOICES):
        raise HttpError(422, f"unknown routing '{payload.routing}'")
    try:
        turn, created = services.enqueue_turn(
            agent=agent,
            origin=payload.origin,
            idempotency_key=payload.idempotency_key,
            prompt=payload.prompt,
            origin_ref=payload.origin_ref,
            routing=payload.routing,
        )
    except services.LaneBusy as exc:
        raise ProblemError(409, "Agent lane busy", detail=str(exc)) from exc
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
def get_turn(request: HttpRequest, turn_id: str):
    return _turn_or_404(turn_id)


@router.post("/turns/{turn_id}/events", response=CountOut)
def append_turn_events(request: HttpRequest, turn_id: str, payload: TurnEventsIn):
    turn = _turn_or_404(turn_id)
    count = services.append_events(turn, [e.dict() for e in payload.events])
    return {"count": count}


@router.get("/turns/{turn_id}/events", response=TurnEventsOut)
def read_turn_events(request: HttpRequest, turn_id: str, after: int = 0):
    turn = _turn_or_404(turn_id)
    events = turn.events.filter(seq__gt=after).order_by("seq")[:500]
    return {"events": list(events)}


@router.post("/turns/{turn_id}/start", response=TurnOut)
def start_turn(request: HttpRequest, turn_id: str, payload: TurnStartIn):
    turn = _turn_or_404(turn_id)
    if turn.status not in (Turn.CLAIMED, Turn.RUNNING):
        raise ProblemError(409, "Turn not startable", detail=f"status={turn.status}")
    return services.mark_running(turn, session_id=payload.session_id)


@router.post("/turns/{turn_id}/finish", response=TurnOut)
def finish_turn(request: HttpRequest, turn_id: str, payload: TurnFinishIn):
    turn = _turn_or_404(turn_id)
    if payload.status not in (Turn.DONE, Turn.FAILED):
        raise HttpError(422, "finish status must be done|failed")
    if turn.status in Turn.TERMINAL:
        return turn  # idempotent finish
    return services.finish_turn(turn, status=payload.status, result_note=payload.result_note)
```

- [ ] **Step 5: Mount the router.** In `apps/api/api.py`, add with the other imports (around the existing router imports):

```python
from apps.harness.api import router as harness_router
```

and with the registrations (after line 173's `session_share_router`):

```python
api.add_router("/harness", harness_router)
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_harness_api.py tests/test_harness_services.py -v`
Expected: all PASS

- [ ] **Step 7: Regenerate frontend API types** (keeps the regen-openapi workflow from churning on the PR)

Run: `cd frontend && npm run gen:api && cd ..`
Expected: `frontend/src/api/generated.ts` updated with `/api/harness/*` paths.

- [ ] **Step 8: Commit**

```bash
git add apps/harness/schemas.py apps/harness/api.py apps/api/api.py tests/test_harness_api.py frontend/src/api/generated.ts
git commit -m "feat(harness): /api/harness runner+turn API with atomic claim and event cursor"
```

---

### Task 5: Runner package — config + control-plane client (stdlib only)

**Files:**
- Create: `packages/canopy_runner/pyproject.toml`, `packages/canopy_runner/canopy_runner/__init__.py`, `packages/canopy_runner/canopy_runner/config.py`, `packages/canopy_runner/canopy_runner/client.py`
- Test: `packages/canopy_runner/tests/test_config.py`, `packages/canopy_runner/tests/test_client.py`

**Interfaces:**
- Produces:
  - `Config.load(path: Path) -> Config` — dataclass with fields `base_url: str`, `token: str`, `runner_id: str`, `emdash_db: str`, `automation_ids: dict[str, str]` (agent slug → emdash automation id), `expected_migration_id: int`, `poll_seconds: int = 20`, `heartbeat_seconds: int = 30`. JSON file; `token` may be `@/path/to/file` meaning "read the file" (so the PAT can live in `~/.claude/canopy/workbench-token`).
  - `Client(base_url, token)` with methods `heartbeat(runner_id, active_turn_ids, degraded=False, note="") -> dict`, `claim(runner_id) -> dict | None` (None on 204), `post_events(turn_id, events) -> None`, `fail_turn(turn_id, note) -> None`. All via `urllib.request`, `Authorization: Bearer <token>`, 10s timeout, raises `ClientError` on non-2xx.

- [ ] **Step 1: Write the failing tests**

```python
# packages/canopy_runner/tests/test_config.py
import json
from pathlib import Path

from canopy_runner.config import Config


def test_load_config_with_token_file(tmp_path: Path):
    token_file = tmp_path / "tok"
    token_file.write_text("sekret\n")
    cfg_file = tmp_path / "runner.json"
    cfg_file.write_text(json.dumps({
        "base_url": "https://labs.example.com/canopy",
        "token": f"@{token_file}",
        "runner_id": "r-1",
        "emdash_db": str(tmp_path / "emdash4.db"),
        "automation_ids": {"echo": "auto-1"},
        "expected_migration_id": 19,
    }))
    cfg = Config.load(cfg_file)
    assert cfg.token == "sekret"
    assert cfg.base_url == "https://labs.example.com/canopy"
    assert cfg.automation_ids["echo"] == "auto-1"
    assert cfg.poll_seconds == 20  # default
```

```python
# packages/canopy_runner/tests/test_client.py
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from canopy_runner.client import Client, ClientError


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.headers["Authorization"] == "Bearer tok"
        if self.path.endswith("/claim"):
            if _Handler.claim_empty:
                self.send_response(204); self.end_headers(); return
            body = json.dumps({"id": "t-1", "status": "claimed"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.endswith("/heartbeat"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "online"}')
            return
        self.send_response(500); self.end_headers()

    def log_message(self, *a):  # quiet
        pass


@pytest.fixture()
def server():
    _Handler.claim_empty = False
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_claim_returns_turn(server):
    c = Client(server, "tok")
    turn = c.claim("r-1")
    assert turn["id"] == "t-1"


def test_claim_returns_none_on_204(server):
    _Handler.claim_empty = True
    c = Client(server, "tok")
    assert c.claim("r-1") is None


def test_error_raises(server):
    c = Client(server, "tok")
    with pytest.raises(ClientError):
        c.post_events("t-1", [{"kind": "status", "payload": {}}])  # handler 500s unknown paths
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd packages/canopy_runner && uv run --with pytest pytest tests/ -v`
Expected: FAIL with import errors.

- [ ] **Step 3: Implement package**

```toml
# packages/canopy_runner/pyproject.toml
[project]
name = "canopy-runner"
version = "0.1.0"
description = "Canopy laptop/cloud runner: claims turns from canopy-web and executes them (emdash adapter first)."
requires-python = ">=3.11"
dependencies = []

[project.scripts]
canopy-runner = "canopy_runner.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

```python
# packages/canopy_runner/canopy_runner/__init__.py
__version__ = "0.1.0"
```

```python
# packages/canopy_runner/canopy_runner/config.py
"""Runner config: one JSON file, stdlib only."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    base_url: str
    token: str
    runner_id: str
    emdash_db: str
    automation_ids: dict[str, str]
    expected_migration_id: int
    poll_seconds: int = 20
    heartbeat_seconds: int = 30
    state_path: str = ""

    @classmethod
    def load(cls, path: Path) -> "Config":
        raw = json.loads(Path(path).read_text())
        token = raw["token"]
        if token.startswith("@"):
            token = Path(token[1:]).expanduser().read_text().strip()
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in raw.items() if k in known}
        kwargs["token"] = token
        cfg = cls(**kwargs)
        if not cfg.state_path:
            cfg.state_path = str(Path(path).with_name("runner-state.json"))
        return cfg
```

```python
# packages/canopy_runner/canopy_runner/client.py
"""Control-plane HTTP client. stdlib urllib; every call is short and synchronous."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

TIMEOUT = 10


class ClientError(Exception):
    pass


class Client:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
        url = f"{self.base_url}/api/harness{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                status = resp.status
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise ClientError(f"{method} {path} -> {exc.code}: {exc.read()[:200]!r}") from exc
        except urllib.error.URLError as exc:
            raise ClientError(f"{method} {path} -> {exc.reason}") from exc
        if status == 204 or not raw:
            return status, None
        return status, json.loads(raw)

    def heartbeat(self, runner_id: str, active_turn_ids: list[str], degraded: bool = False, note: str = "") -> dict:
        _, payload = self._call(
            "POST",
            f"/runners/{runner_id}/heartbeat",
            {"active_turn_ids": active_turn_ids, "degraded": degraded, "note": note},
        )
        return payload or {}

    def claim(self, runner_id: str) -> dict | None:
        status, payload = self._call("POST", f"/runners/{runner_id}/claim")
        return payload if status == 200 else None

    def post_events(self, turn_id: str, events: list[dict]) -> None:
        self._call("POST", f"/turns/{turn_id}/events", {"events": events})

    def fail_turn(self, turn_id: str, note: str) -> None:
        self._call("POST", f"/turns/{turn_id}/finish", {"status": "failed", "result_note": note})
```

Create `packages/canopy_runner/tests/__init__.py` (empty).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd packages/canopy_runner && uv run --with pytest pytest tests/ -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add packages/canopy_runner
git commit -m "feat(runner): canopy_runner package — config + stdlib control-plane client"
```

---

### Task 6: Runner package — emdash adapter (schema guard, run injection, type-flip)

**Files:**
- Create: `packages/canopy_runner/canopy_runner/emdash.py`
- Test: `packages/canopy_runner/tests/test_emdash.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure sqlite3).
- Produces (Task 7 main loop calls these):
  - `class SchemaDrift(Exception)`
  - `check_schema(db_path: str, expected_migration_id: int) -> None` — raises `SchemaDrift` when `MAX(id)` in `__drizzle_migrations` != expected.
  - `inject_run(db_path: str, automation_id: str, run_id: str, task_name: str) -> None` — INSERTs a `queued`/`manual` `automation_runs` row, snapshots copied from the automation row (verified live 2026-07-05: the scheduler drains `status='queued'` regardless of trigger_kind; runtime reads config from the automation row, snapshots are audit-only).
  - `find_task(db_path: str, automation_run_id: str) -> dict | None` — `{id, name, status}` of the emdash task created for the run, or None while pending.
  - `promote_task(db_path: str, task_id: str) -> None` — `UPDATE tasks SET type='task'` (byte-identical to emdash's own convert action).
  - `run_status(db_path: str, run_id: str) -> str | None` — the automation_run's status.

- [ ] **Step 1: Write the failing tests** (fixture builds a miniature emdash4 schema — just the four tables/columns the adapter touches)

```python
# packages/canopy_runner/tests/test_emdash.py
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from canopy_runner.emdash import (
    SchemaDrift,
    check_schema,
    find_task,
    inject_run,
    promote_task,
    run_status,
)

AUTOMATION_ID = "auto-1"


@pytest.fixture()
def db(tmp_path: Path) -> str:
    path = tmp_path / "emdash4.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE __drizzle_migrations (id INTEGER PRIMARY KEY, hash TEXT, created_at INTEGER);
        INSERT INTO __drizzle_migrations (id, hash, created_at) VALUES (19, 'h', 0);
        CREATE TABLE automations (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, task_config TEXT, project_id TEXT,
          enabled INTEGER DEFAULT 1 NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
          trigger_config TEXT, conversation_config TEXT, deleted_at INTEGER
        );
        CREATE TABLE automation_runs (
          id TEXT PRIMARY KEY, automation_id TEXT NOT NULL, scheduled_at INTEGER, deadline_at INTEGER,
          started_at INTEGER, task_created_at INTEGER, launched_at INTEGER, finished_at INTEGER,
          status TEXT NOT NULL, error TEXT, trigger_kind TEXT NOT NULL,
          trigger_config_snapshot TEXT DEFAULT '{}' NOT NULL,
          conversation_config_snapshot TEXT DEFAULT '{}' NOT NULL,
          task_config_snapshot TEXT, generated_task_name TEXT
        );
        CREATE TABLE tasks (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
          type TEXT DEFAULT 'task' NOT NULL, automation_run_id TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO automations (id, name, task_config, project_id, enabled, created_at, updated_at, conversation_config) "
        "VALUES (?, 'canopy-turns', ?, 'proj-1', 1, 0, 0, ?)",
        (
            AUTOMATION_ID,
            json.dumps({"version": "1", "taskConfig": {"version": "1", "name": "t"}, "workspaceConfig": {}}),
            json.dumps({"prompt": "/canopy:drain-turn echo", "provider": "claude", "autoApprove": False, "type": "pty"}),
        ),
    )
    conn.commit()
    conn.close()
    return str(path)


def test_check_schema_ok(db):
    check_schema(db, 19)  # no raise


def test_check_schema_drift_raises(db):
    with pytest.raises(SchemaDrift):
        check_schema(db, 18)


def test_inject_run_copies_snapshots(db):
    rid = str(uuid.uuid4())
    inject_run(db, AUTOMATION_ID, rid, task_name="canopy-turn-echo")
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, trigger_kind, conversation_config_snapshot, generated_task_name "
        "FROM automation_runs WHERE id=?", (rid,)
    ).fetchone()
    assert row[0] == "queued" and row[1] == "manual"
    assert json.loads(row[2])["prompt"] == "/canopy:drain-turn echo"
    assert row[3] == "canopy-turn-echo"
    assert run_status(db, rid) == "queued"


def test_inject_refuses_unknown_automation(db):
    with pytest.raises(ValueError):
        inject_run(db, "nope", str(uuid.uuid4()), task_name="x")


def test_find_and_promote_task(db):
    rid = str(uuid.uuid4())
    inject_run(db, AUTOMATION_ID, rid, task_name="x")
    assert find_task(db, rid) is None
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tasks (id, project_id, name, status, type, automation_run_id) "
        "VALUES ('task-1', 'proj-1', 'fruity', 'in_progress', 'automation-run', ?)", (rid,)
    )
    conn.commit(); conn.close()
    task = find_task(db, rid)
    assert task == {"id": "task-1", "name": "fruity", "status": "in_progress", "type": "automation-run"}
    promote_task(db, "task-1")
    assert find_task(db, rid)["type"] == "task"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd packages/canopy_runner && uv run --with pytest pytest tests/test_emdash.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement the adapter**

```python
# packages/canopy_runner/canopy_runner/emdash.py
"""Emdash adapter: trigger a visible emdash session by inserting a queued
automation run. Unsupported-surface rules:

- NEVER write when the Drizzle migration id differs from the vetted pin.
- Only two writes exist: INSERT into automation_runs, UPDATE tasks.type.
- Everything else (task creation, worktree, session spawn) is emdash's own
  runtime reacting to the queued row — verified by live experiment 2026-07-05.
"""
from __future__ import annotations

import json
import sqlite3
import time


class SchemaDrift(Exception):
    """emdash migrated its DB; injection is disabled until re-vetted."""


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=3.0)
    conn.row_factory = sqlite3.Row
    return conn


def check_schema(db_path: str, expected_migration_id: int) -> None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT MAX(id) AS m FROM __drizzle_migrations").fetchone()
    actual = row["m"] if row else None
    if actual != expected_migration_id:
        raise SchemaDrift(
            f"emdash migration id {actual} != vetted {expected_migration_id}; refusing to write"
        )


def inject_run(db_path: str, automation_id: str, run_id: str, task_name: str) -> None:
    now_ms = int(time.time() * 1000)
    with _connect(db_path) as conn:
        auto = conn.execute(
            "SELECT id, task_config, conversation_config, enabled, deleted_at FROM automations WHERE id=?",
            (automation_id,),
        ).fetchone()
        if auto is None or auto["deleted_at"] is not None:
            raise ValueError(f"automation {automation_id} not found in {db_path}")
        if not auto["enabled"]:
            raise ValueError(f"automation {automation_id} is disabled")
        conn.execute(
            "INSERT INTO automation_runs (id, automation_id, scheduled_at, deadline_at, started_at,"
            " task_created_at, launched_at, finished_at, status, error, trigger_kind,"
            " trigger_config_snapshot, conversation_config_snapshot, task_config_snapshot, generated_task_name)"
            " VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, 'queued', NULL, 'manual', '{}', ?, ?, ?)",
            (
                run_id,
                automation_id,
                now_ms,
                auto["conversation_config"] or "{}",
                auto["task_config"],
                task_name,
            ),
        )
        conn.commit()


def run_status(db_path: str, run_id: str) -> str | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT status FROM automation_runs WHERE id=?", (run_id,)).fetchone()
    return row["status"] if row else None


def find_task(db_path: str, automation_run_id: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, name, status, type FROM tasks WHERE automation_run_id=?",
            (automation_run_id,),
        ).fetchone()
    return dict(row) if row else None


def promote_task(db_path: str, task_id: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE tasks SET type='task', updated_at=datetime('now') WHERE id=?", (task_id,)
        )
        conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd packages/canopy_runner && uv run --with pytest pytest tests/test_emdash.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add packages/canopy_runner/canopy_runner/emdash.py packages/canopy_runner/tests/test_emdash.py
git commit -m "feat(runner): emdash adapter — schema guard, queued-run injection, task promote"
```

---

### Task 7: Runner package — main loop (heartbeat, claim, execute, crash-safe state)

**Files:**
- Create: `packages/canopy_runner/canopy_runner/main.py`
- Test: `packages/canopy_runner/tests/test_main.py`

**Interfaces:**
- Consumes: `Config`, `Client`, and the `emdash` module functions (exact signatures from Tasks 5-6).
- Produces: `run_once(cfg, client, now_fn=time.time) -> str` — one iteration; returns a short action string for logging/tests (`"degraded"`, `"idle"`, `"injected:<turn_id>"`, `"promoted:<task_id>"`). `main()` — argparse (`--config`, `--once`), loop with heartbeat cadence, local state file for crash-safe rehydration (`{"active": {turn_id: {"emdash_run_id":…, "agent":…, "task_promoted": bool}}}`).

- [ ] **Step 1: Write the failing tests** (drive `run_once` with a fake client + the sqlite fixture from Task 6, copied here — tests must be readable standalone)

```python
# packages/canopy_runner/tests/test_main.py
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from canopy_runner.config import Config
from canopy_runner.main import run_once

AUTOMATION_ID = "auto-1"


@pytest.fixture()
def db(tmp_path: Path) -> str:
    path = tmp_path / "emdash4.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE __drizzle_migrations (id INTEGER PRIMARY KEY, hash TEXT, created_at INTEGER);
        INSERT INTO __drizzle_migrations (id, hash, created_at) VALUES (19, 'h', 0);
        CREATE TABLE automations (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, task_config TEXT, project_id TEXT,
          enabled INTEGER DEFAULT 1 NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
          trigger_config TEXT, conversation_config TEXT, deleted_at INTEGER
        );
        CREATE TABLE automation_runs (
          id TEXT PRIMARY KEY, automation_id TEXT NOT NULL, scheduled_at INTEGER, deadline_at INTEGER,
          started_at INTEGER, task_created_at INTEGER, launched_at INTEGER, finished_at INTEGER,
          status TEXT NOT NULL, error TEXT, trigger_kind TEXT NOT NULL,
          trigger_config_snapshot TEXT DEFAULT '{}' NOT NULL,
          conversation_config_snapshot TEXT DEFAULT '{}' NOT NULL,
          task_config_snapshot TEXT, generated_task_name TEXT
        );
        CREATE TABLE tasks (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
          type TEXT DEFAULT 'task' NOT NULL, automation_run_id TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO automations (id, name, task_config, project_id, enabled, created_at, updated_at, conversation_config) "
        "VALUES (?, 'canopy-turns', ?, 'proj-1', 1, 0, 0, ?)",
        (
            AUTOMATION_ID,
            json.dumps({"version": "1", "taskConfig": {"version": "1", "name": "t"}, "workspaceConfig": {}}),
            json.dumps({"prompt": "/canopy:drain-turn echo", "provider": "claude", "autoApprove": False, "type": "pty"}),
        ),
    )
    conn.commit()
    conn.close()
    return str(path)


class FakeClient:
    def __init__(self, turns=None):
        self.turns = list(turns or [])
        self.events = []
        self.heartbeats = []
        self.failed = []

    def heartbeat(self, runner_id, active_turn_ids, degraded=False, note=""):
        self.heartbeats.append((runner_id, list(active_turn_ids), degraded, note))
        return {"status": "degraded" if degraded else "online"}

    def claim(self, runner_id):
        return self.turns.pop(0) if self.turns else None

    def post_events(self, turn_id, events):
        self.events.append((turn_id, events))

    def fail_turn(self, turn_id, note):
        self.failed.append((turn_id, note))


def _cfg(db, tmp_path):
    return Config(
        base_url="http://x", token="t", runner_id="r-1", emdash_db=db,
        automation_ids={"echo": AUTOMATION_ID}, expected_migration_id=19,
        state_path=str(tmp_path / "state.json"),
    )


def test_idle_when_no_work(db, tmp_path):
    client = FakeClient()
    assert run_once(_cfg(db, tmp_path), client) == "idle"
    assert client.heartbeats  # heartbeat always sent


def test_claim_injects_run_and_reports_events(db, tmp_path):
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    result = run_once(_cfg(db, tmp_path), client)
    assert result == "injected:t-1"
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM automation_runs").fetchone()[0] == 1
    kinds = [e["kind"] for _, evs in client.events for e in evs]
    assert "status" in kinds  # injected event posted
    # state file records the active turn for crash-safe rehydration
    state = json.loads(Path(_cfg(db, tmp_path).state_path).read_text())
    assert "t-1" in state["active"]


def test_unknown_agent_fails_turn(db, tmp_path):
    client = FakeClient(turns=[{"id": "t-2", "agent_slug": "eva", "status": "claimed"}])
    result = run_once(_cfg(db, tmp_path), client)
    assert result == "failed:t-2"
    assert client.failed and client.failed[0][0] == "t-2"


def test_schema_drift_goes_degraded_and_never_writes(db, tmp_path):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO __drizzle_migrations (id, hash, created_at) VALUES (20, 'x', 0)")
    conn.commit(); conn.close()
    client = FakeClient(turns=[{"id": "t-3", "agent_slug": "echo", "status": "claimed"}])
    result = run_once(_cfg(db, tmp_path), client)
    assert result == "degraded"
    assert client.heartbeats[-1][2] is True  # degraded flag
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM automation_runs").fetchone()[0] == 0


def test_promotes_task_on_followup_pass(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    run_once(cfg, client)  # inject
    state = json.loads(Path(cfg.state_path).read_text())
    run_id = state["active"]["t-1"]["emdash_run_id"]
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tasks (id, project_id, name, status, type, automation_run_id) "
        "VALUES ('task-1', 'proj-1', 'fruity', 'in_progress', 'automation-run', ?)", (run_id,)
    )
    conn.commit(); conn.close()
    result = run_once(cfg, client)  # follow-up pass sees the task
    assert result == "promoted:task-1"
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT type FROM tasks WHERE id='task-1'").fetchone()[0] == "task"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd packages/canopy_runner && uv run --with pytest pytest tests/test_main.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement the loop**

```python
# packages/canopy_runner/canopy_runner/main.py
"""Runner main loop.

One iteration (run_once):
  1. schema guard — drift => heartbeat(degraded) and do nothing else
  2. heartbeat with the active turn ids (renews leases)
  3. follow-up pass over active turns: promote freshly-created emdash tasks
     to sidebar type='task'; drop finished/lost turns from local state
  4. claim at most one new turn; inject the emdash automation run; record
     state; post ledger events

State file makes restarts safe: on boot we re-read it and resume watching
already-injected turns instead of double-injecting.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import uuid
from pathlib import Path

from . import emdash
from .client import Client, ClientError
from .config import Config

logger = logging.getLogger("canopy_runner")


def _load_state(cfg: Config) -> dict:
    p = Path(cfg.state_path)
    if p.exists():
        return json.loads(p.read_text())
    return {"active": {}}


def _save_state(cfg: Config, state: dict) -> None:
    Path(cfg.state_path).write_text(json.dumps(state, indent=2))


def run_once(cfg: Config, client: Client, now_fn=time.time) -> str:
    state = _load_state(cfg)
    active_ids = list(state["active"].keys())

    # 1. schema guard
    try:
        emdash.check_schema(cfg.emdash_db, cfg.expected_migration_id)
    except emdash.SchemaDrift as exc:
        logger.error("schema drift: %s", exc)
        client.heartbeat(cfg.runner_id, active_ids, degraded=True, note=str(exc))
        return "degraded"

    # 2. heartbeat (renews leases for active turns)
    client.heartbeat(cfg.runner_id, active_ids)

    # 3. follow-up pass: promote new emdash tasks, forget stale entries
    for turn_id, info in list(state["active"].items()):
        task = emdash.find_task(cfg.emdash_db, info["emdash_run_id"])
        if task and not info.get("task_promoted"):
            emdash.promote_task(cfg.emdash_db, task["id"])
            info["task_promoted"] = True
            _save_state(cfg, state)
            try:
                client.post_events(turn_id, [{
                    "kind": "status",
                    "payload": {"status": "emdash_task", "task_id": task["id"], "task_name": task["name"]},
                }])
            except ClientError as exc:
                logger.warning("event post failed for %s: %s", turn_id, exc)
            return f"promoted:{task['id']}"
        run_st = emdash.run_status(cfg.emdash_db, info["emdash_run_id"])
        if run_st in ("failed", "skipped"):
            try:
                client.fail_turn(turn_id, f"emdash run {run_st}")
            except ClientError as exc:
                logger.warning("fail_turn failed for %s: %s", turn_id, exc)
            del state["active"][turn_id]
            _save_state(cfg, state)
            return f"failed:{turn_id}"

    # 4. claim new work (one turn per iteration keeps the loop simple)
    try:
        turn = client.claim(cfg.runner_id)
    except ClientError as exc:
        logger.warning("claim failed: %s", exc)
        return "idle"
    if turn is None:
        return "idle"

    turn_id = turn["id"]
    agent = turn.get("agent_slug", "")
    automation_id = cfg.automation_ids.get(agent)
    if not automation_id:
        try:
            client.fail_turn(turn_id, f"no emdash automation configured for agent '{agent}'")
        except ClientError as exc:
            logger.warning("fail_turn failed: %s", exc)
        return f"failed:{turn_id}"

    emdash_run_id = str(uuid.uuid4())
    emdash.inject_run(
        cfg.emdash_db, automation_id, emdash_run_id, task_name=f"canopy-turn-{agent}"
    )
    state["active"][turn_id] = {
        "emdash_run_id": emdash_run_id,
        "agent": agent,
        "task_promoted": False,
    }
    _save_state(cfg, state)
    try:
        client.post_events(turn_id, [{
            "kind": "status",
            "payload": {"status": "injected", "emdash_run_id": emdash_run_id},
        }])
    except ClientError as exc:
        logger.warning("event post failed: %s", exc)
    return f"injected:{turn_id}"


def main() -> None:
    parser = argparse.ArgumentParser(description="canopy runner (emdash adapter)")
    parser.add_argument("--config", required=True)
    parser.add_argument("--once", action="store_true", help="single iteration (for cron/tests)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = Config.load(Path(args.config))
    client = Client(cfg.base_url, cfg.token)
    if args.once:
        print(run_once(cfg, client))
        return
    while True:
        try:
            run_once(cfg, client)
        except Exception:  # noqa: BLE001 — the loop must survive anything
            logger.exception("run_once crashed; continuing")
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all runner tests**

Run: `cd packages/canopy_runner && uv run --with pytest pytest tests/ -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add packages/canopy_runner/canopy_runner/main.py packages/canopy_runner/tests/test_main.py
git commit -m "feat(runner): main loop — heartbeat, claim, inject, promote, crash-safe state"
```

---

### Task 8: Turn completion cleanup + finished-turn state eviction

The main loop keeps watching turns the claude session already finished (the drain-turn skill POSTs `/finish`). Evict terminal turns from local state so `active_turn_ids` stays truthful and leases stop being renewed for finished work.

**Files:**
- Modify: `packages/canopy_runner/canopy_runner/client.py` (add `get_turn`), `packages/canopy_runner/canopy_runner/main.py` (evict terminal turns in the follow-up pass)
- Test: `packages/canopy_runner/tests/test_main.py` (add test)

**Interfaces:**
- Produces: `Client.get_turn(turn_id) -> dict` (`GET /turns/{id}`); loop evicts state entries whose turn status is `done|failed|lost`.

- [ ] **Step 1: Add the failing test** (append to `tests/test_main.py`)

```python
def test_evicts_turn_finished_serverside(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    client.turn_lookup = {"t-1": {"id": "t-1", "status": "done"}}
    run_once(cfg, client)  # inject
    result = run_once(cfg, client)  # follow-up sees server-side done
    assert result == "evicted:t-1"
    state = json.loads(Path(cfg.state_path).read_text())
    assert state["active"] == {}
```

And extend `FakeClient` with:

```python
    turn_lookup: dict = {}

    def get_turn(self, turn_id):
        return self.turn_lookup.get(turn_id, {"id": turn_id, "status": "running"})
```

(Note: `test_promotes_task_on_followup_pass` runs the follow-up before any task exists; the default `running` lookup keeps its behavior unchanged.)

- [ ] **Step 2: Run to verify the new test fails**

Run: `cd packages/canopy_runner && uv run --with pytest pytest tests/test_main.py -v`
Expected: new test FAILs (`AttributeError: get_turn` on the real path / wrong result string)

- [ ] **Step 3: Implement.** In `client.py` add:

```python
    def get_turn(self, turn_id: str) -> dict:
        _, payload = self._call("GET", f"/turns/{turn_id}")
        return payload or {}
```

In `main.py`, at the TOP of the follow-up loop body (before the promote logic), add:

```python
        try:
            remote = client.get_turn(turn_id)
        except ClientError:
            remote = {"status": "running"}
        if remote.get("status") in ("done", "failed", "lost"):
            del state["active"][turn_id]
            _save_state(cfg, state)
            return f"evicted:{turn_id}"
```

- [ ] **Step 4: Run all runner tests**

Run: `cd packages/canopy_runner && uv run --with pytest pytest tests/ -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add packages/canopy_runner
git commit -m "feat(runner): evict server-finished turns from local state"
```

---

### Task 9: drain-turn skill (canopy plugin repo) + runner install docs

**Files (different repo — `~/emdash-projects/canopy`):**
- Create: `~/emdash-projects/canopy/plugins/canopy/skills/drain-turn/SKILL.md`
**Files (this repo):**
- Create: `packages/canopy_runner/README.md`, `packages/canopy_runner/launchd/com.canopy.runner.plist`

**Interfaces:**
- Consumes: `/api/harness/turns/*` endpoints (Task 4) and the PAT at `~/.claude/canopy/workbench-token`.
- Produces: the skill the emdash automation prompt invokes (`/canopy:drain-turn <agent-slug>`).

- [ ] **Step 1: Write the skill** (in the canopy plugin repo)

````markdown
---
name: drain-turn
description: >
  Execute one canopy-web harness turn for an agent: resolve the active turn,
  mark it running, drain the agent's pending board commands, then finish the
  turn. Invoked by the emdash automation the canopy runner triggers — this
  skill IS the body of an automated agent turn. Usage: /canopy:drain-turn <agent-slug>
---

# drain-turn

You are executing ONE automated turn for agent `$1` against canopy-web.

Base URL: read `CANOPY_WEB_URL` from the environment; default
`https://labs.connect.dimagi.com/canopy`. Auth: `Authorization: Bearer $(cat ~/.claude/canopy/workbench-token)` on every call.

## Steps

1. **Resolve the turn.** `GET {base}/api/harness/turns/?agent=$1&status=claimed,running`.
   Exactly one turn is expected (the harness enforces one active turn per agent).
   - Zero turns → say "no active turn for $1" and STOP. Do not invent work.
   - Note the turn `id` and `prompt`.
2. **Mark it running.** `POST {base}/api/harness/turns/{id}/start` with
   `{"session_id": ""}`.
3. **Do the work.** If the turn `prompt` is non-empty, follow it. Otherwise the
   default work is a board drain:
   `GET {base}/api/agents/$1/commands?status=pending` — for each command, act
   under your normal guardrails (the same rules as a human-triggered turn:
   writes gated, no external sends without approval), then
   `POST {base}/api/agents/$1/commands/{cmd_id}/apply` with a one-line
   `result_note`.
4. **Report.** Append a short ledger event:
   `POST {base}/api/harness/turns/{id}/events` with
   `{"events": [{"kind": "status", "payload": {"status": "work_summary", "summary": "<one line>"}}]}`.
5. **Finish.** `POST {base}/api/harness/turns/{id}/finish` with
   `{"status": "done", "result_note": "<n> commands applied"}` — or
   `{"status": "failed", "result_note": "<why>"}` if the work errored.
   NEVER leave the turn unfinished: if you must stop early, finish with
   `failed` and an honest note.
````

- [ ] **Step 2: Commit the skill** (canopy plugin repo)

```bash
cd ~/emdash-projects/canopy
git add plugins/canopy/skills/drain-turn
git commit -m "feat(skills): drain-turn — body of an automated harness turn"
```

- [ ] **Step 3: Write runner install docs + launchd plist** (back in canopy-web)

```xml
<!-- packages/canopy_runner/launchd/com.canopy.runner.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.canopy.runner</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>python3</string>
    <string>-m</string>
    <string>canopy_runner.main</string>
    <string>--config</string>
    <string>/Users/jjackson/.canopy/runner.json</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/jjackson/.canopy/runner.log</string>
  <key>StandardErrorPath</key><string>/Users/jjackson/.canopy/runner.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>/Users/jjackson/emdash-projects/canopy-web/packages/canopy_runner</string>
  </dict>
</dict>
</plist>
```

````markdown
# packages/canopy_runner/README.md

# canopy-runner

Laptop/cloud executor for canopy-web harness turns. Emdash adapter: triggers a
visible interactive claude session in emdash by inserting a queued automation
run (see the spec: docs/superpowers/specs/2026-07-05-agent-execution-control-plane-design.md).

## One-time laptop setup

1. **Create the emdash automation** (emdash UI → Automations → New), one per agent:
   - Name: `canopy — automated turn execution (echo)`
   - Project: the agent's repo; Workspace: repo root or a persistent workspace
   - Schedule: none/disabled (the runner triggers runs; cron stays off)
   - Prompt: `/canopy:drain-turn echo`
   - Provider: claude, terminal (pty) mode
   Copy the automation id:
   `sqlite3 ~/Library/Application\ Support/Emdash/emdash4.db "SELECT id,name FROM automations;"`
2. **Pair the runner**:
   `curl -X POST {base}/api/harness/runners/ -H "Authorization: Bearer $(cat ~/.claude/canopy/workbench-token)" -H 'Content-Type: application/json' -d '{"name":"jj-mbp","kind":"emdash","capabilities":{"agents":["echo"]}}'`
   — note the returned `id`.
3. **Write `~/.canopy/runner.json`**:
   ```json
   {
     "base_url": "https://labs.connect.dimagi.com/canopy",
     "token": "@~/.claude/canopy/workbench-token",
     "runner_id": "<uuid from step 2>",
     "emdash_db": "/Users/jjackson/Library/Application Support/Emdash/emdash4.db",
     "automation_ids": {"echo": "<automation id from step 1>"},
     "expected_migration_id": 19
   }
   ```
   (`expected_migration_id`: `sqlite3 .../emdash4.db "SELECT MAX(id) FROM __drizzle_migrations;"` — re-vet after every emdash update; the runner goes `degraded` instead of writing when it drifts.)
4. **Install launchd job**:
   `cp launchd/com.canopy.runner.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.canopy.runner.plist`
5. **Smoke test**: `python3 -m canopy_runner.main --config ~/.canopy/runner.json --once` → `idle`.

## E2E check (Phase 0 exit criterion)

1. `curl -X POST {base}/api/harness/turns/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"agent_slug":"echo","origin":"manual","idempotency_key":"e2e-'$(date +%s)'"}'`
2. Within ~2 min: an emdash session appears (Automations panel immediately; sidebar after promote) running `/canopy:drain-turn echo`.
3. `GET {base}/api/harness/turns/{id}` → `done`, with events `queued → claimed → injected → emdash_task → running → work_summary → done`.
4. Close the laptop, enqueue another turn → it stays `queued`; reopen → it executes.
````

- [ ] **Step 4: Commit** (canopy-web repo)

```bash
git add packages/canopy_runner/README.md packages/canopy_runner/launchd
git commit -m "docs(runner): laptop install (emdash automation, pairing, launchd) + e2e checklist"
```

---

### Task 10: Full-suite pass + PR

**Files:** none new.

- [ ] **Step 1: Run the whole backend suite**

Run: `uv run pytest`
Expected: all PASS (pre-existing failures, if any, must match main — check `git stash && uv run pytest` if unsure).

- [ ] **Step 2: Frontend build check**

Run: `cd frontend && npm run build`
Expected: builds clean (generated.ts from Task 4 Step 7 type-checks).

- [ ] **Step 3: Push branch + open PR**

```bash
git push -u origin HEAD
gh pr create --title "Agent execution harness Phase 0: laptop loop (apps/harness + canopy_runner)" --body "$(cat <<'EOF'
## Summary
- New framework-tier app `apps/harness`: Runner registry, Turn lifecycle (atomic claim + 15-min leases + one-active-turn-per-agent), TurnEvent ledger with cursor reads — mounted at `/api/harness/`.
- New `packages/canopy_runner`: stdlib-only laptop daemon — heartbeat, claim, emdash trigger via queued automation-run injection (schema-guarded, degrades loud on drift), sidebar task promotion, crash-safe local state.
- drain-turn skill (canopy plugin repo) is the body of an automated turn: resolve → start → drain board commands → finish.
- Spec: docs/superpowers/specs/2026-07-05-agent-execution-control-plane-design.md (Phase 0).

## Test plan
- [ ] `uv run pytest` (new: test_harness_models/services/api)
- [ ] `cd packages/canopy_runner && uv run --with pytest pytest tests/`
- [ ] Manual e2e per packages/canopy_runner/README.md (laptop open/closed)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (already applied)

- **Spec coverage:** §5.1 Runner/Turn/TurnEvent → Tasks 2-4; §5.2 router (pull-claim, lease, local_only-waits) → Tasks 3-4; §5.3 API → Task 4 (approvals + degraded endpoint deferred to Phase 1 — `degraded` rides the heartbeat body instead of a separate route, simpler and sufficient); §6.1 emdash adapter → Tasks 6-8; drain-turn + lean runner docs → Task 9; §8 failure table → lease sweep (T3), schema guard (T6), crash-safe state (T7), eviction (T8); §10 boundary → Task 2 Step 4. Approval model, Slack, agent_runs mirroring, cloud runner: Phases 1-2, intentionally absent.
- **Type consistency:** `claim` returns TurnOut with `agent_slug` (runner reads `turn["agent_slug"]` in Task 7) — matches Task 4 schema resolver. Event dicts are `{kind, payload}` everywhere. Finish statuses `done|failed` only; `lost` is server-side.
- **Fixed in review:** `GET /turns/` originally sliced before filtering (would `TypeError` on the drain-turn skill's `?agent&status` query) — now filters first, slices last, with a dedicated test.
