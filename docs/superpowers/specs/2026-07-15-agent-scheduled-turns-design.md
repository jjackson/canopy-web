# Agent scheduled turns — design

**Date:** 2026-07-15
**Status:** Approved, not yet implemented
**Tier:** Framework (`apps/harness`)

## Problem

Recurring agent activities have no home. Eva's goal review and Echo's weekly
manager report are things Jonathan wants to happen on a cadence, but today the
only way to run them is to remember to type the command. The concept exists in
emdash *automations*, but it lives on one laptop, isn't visible or editable
server-side, and has no notion of chasing the human.

The goal is not merely "run a turn on a cron." It is **automating Jonathan into
doing these things**. The failure mode being designed against is not the agent
failing to run — it is Jonathan not finishing out the session the run spawns.

## Goals

- Declare recurring turns per agent, stored server-side, visible and editable in
  the Agent UI.
- Fire them automatically on the fleet's existing execution path.
- Nag when an occurrence goes unfinished, then give up.
- Manually trigger a schedule off-cycle ("Run now").
- Leave room for multiple notification channels without building them all now.

## Non-goals (deliberate, additive later)

- Per-schedule escalation policy (nag harder over time).
- Catch-up/backfill of missed occurrences.
- Notification channels beyond the inbox projection.
- Cross-agent (Ada-style) fan-out scheduling. `target_agent != self` belongs to
  the paused dispatch-item unification work (its item (b)), not here.

## The constraint that shapes the design

`apps/harness/models.py` enforces:

```python
models.UniqueConstraint(fields=["agent"],
    condition=models.Q(status__in=["claimed", "running", "needs_human"]),
    name="one_executing_turn_per_agent")
```

One executing turn per agent. An abandoned goal-review session — precisely the
case the nag exists for — parks a turn in `running`/`needs_human` and **wedges
the agent entirely**. The existing lease sweep does not rescue it: the runner's
heartbeat reports the turn in `active_turn_ids` and keeps renewing the lease for
as long as the emdash session is open.

**Consequence:** the nag cannot be "leave the turn open and remind him." An
unattended cron turn must be **released** — terminated as `missed`, freeing the
agent — while the nag survives on the schedule.

## Model

One new table, `AgentSchedule`, in `apps/harness` (framework tier — it references
`agents.Agent` and `workspaces.Workspace`, never product apps).

| Field | Type | Purpose |
|---|---|---|
| `id` | UUID pk | |
| `agent` | FK `agents.Agent` | owner |
| `workspace` | FK `workspaces.Workspace` | tenant |
| `name` | char(200) | "Weekly manager report" |
| `prompt` | text | what the turn is seeded with, e.g. `/echo:manager-report` |
| `cron` | char(120) | 5-field cron expression |
| `timezone` | char(64) | IANA tz, e.g. `America/New_York` |
| `enabled` | bool | pause without deleting |
| `routing` | char | reuses `Turn.ROUTING_CHOICES`, default `prefer_local` |
| `grace_minutes` | int | how long an unattended turn may hold the agent (default 120) |
| `notify` | JSON list | channel ids — the extensibility seam |
| `last_slot` | datetime, null | newest slot fired; supersede + no-backfill anchor |
| `created_at` / `updated_at` | | |

### No occurrence table

The `Turn` **is** the occurrence:

- `origin = "cron"` (the value already exists in `Turn.ORIGIN_CHOICES`)
- `origin_ref = {"schedule_id": …, "slot": "2026-07-17T09:00:00-04:00"}`
- `idempotency_key = f"sched:{schedule_id}:{slot}"`

History for a schedule is its cron turns. This is deliberate:
The dispatch-item unification analysis records that canopy-web already has three
half-overlapping representations of "a thing that needs addressing"; an
occurrence row would be a fourth. The nag is a *projection* (below), not an
object.

### One additive change to `Turn`

Add a `MISSED` terminal status (`STATUS_CHOICES` + `TERMINAL`), and allow
`finish_turn()` to target it.

`LOST` is not reusable: it means "lease expired, we lost track of this," so
reusing it would make "you skipped your goal review" indistinguishable from an
infrastructure failure in both the ledger and the UI.

## Firing — runner-owned, config server-side

The runner already polls `claim` continuously; it gains a schedule cache.

1. `GET /api/harness/schedules/?agent=…` → runner caches locally, refreshed per
   poll cycle.
2. Runner evaluates each enabled schedule with `croniter` (new dependency)
   against `now` in the schedule's `timezone`.
3. A due slot → `POST /api/harness/schedules/{id}/fire {slot}` → the server calls
   the **existing** `services.enqueue_turn(origin=CRON, idempotency_key=…)`.

The scheduler is a *producer of turns*, not a second execution engine.

### Why two runners racing is safe

Jonathan fails over between two macOS accounts (he switches accounts on token exhaustion), so both
runners may evaluate the same schedule and fire the same slot. Both produce an
identical `idempotency_key`, and `enqueue_turn()` already treats that exact
collision as a replay and returns the existing turn (it handles both the
pre-check and the `IntegrityError` race). The invariant does the coordinating —
no leader election, no locking.

### No backfill

The runner fires only the **most recent** due slot. Laptop off for three weeks →
one goal review, not three. `last_slot` is the anchor.

## Supersede and release

Both happen server-side inside the `fire` transaction. They are the same idea at
two timescales:

- **Supersede:** firing slot N finds the schedule's prior non-terminal turn and
  calls `finish_turn(status=MISSED, result_note="superseded by <slot>")`. You
  only ever owe the newest occurrence.
- **Release:** a cron turn unattended past `grace_minutes` gets the same
  transition. This is what unwedges the agent, and it runs on the tick, so it
  needs no new infrastructure.

**Supersede *is* the give-up.** The recurrence already defines the nag window — a
weekly report nags for a week, then next Friday supersedes it. No separate
"give up after N days" knob.

## The nag — a projection

`apps/agents/services.py::needs_you()` gains a source: for each enabled schedule,
if its latest turn is not `done`, emit a typed item (`ref_kind="schedule"`)
carrying a **Run now** action. It lands in the existing `waiting_count` badge the
menu-bar runner panel already renders — the surface Jonathan already looks at —
with no new plumbing and no new model.

## Notification seam

`notify` is a list of channel ids resolved through a string registry, copying the
pattern `apps/timeline/sources.py` already uses to read other apps' events
without importing them.

Ship **one** channel: `inbox` (the projection above). Email / macOS notification
/ Slack later become a registry entry plus a function — no model change. Proving
the seam with one channel beats building four that haven't been chosen.

## Manual trigger

`POST /api/agents/{slug}/schedules/{id}/run-now` → same `enqueue_turn`, but
`origin="manual"` and `idempotency_key = f"sched:{id}:manual:{uuid4}"`, so an
ad-hoc run never collides with — or satisfies — a real slot.

## API

Split by audience. Human CRUD is agent-scoped (matching every other agent
sub-resource); machine firing stays on the harness router beside
`claim`/`heartbeat`.

```
GET|POST      /api/agents/{slug}/schedules/           # list / create
PATCH|DELETE  /api/agents/{slug}/schedules/{id}       # edit / remove
POST          /api/agents/{slug}/schedules/{id}/run-now
GET           /api/harness/schedules/?agent=…         # runner sync
POST          /api/harness/schedules/{id}/fire        # runner materializes a slot
```

### Mounting

`apps/harness` grows a **second router**, `schedules_router`, mounted on the
agents namespace exactly as `agent_runs` already is:

```python
api.add_router("/agents", agents_router)
api.add_router("/agents", agent_runs_router)
api.add_router("/agents", schedules_router)   # new
api.add_router("/harness", harness_router)    # unchanged
```

No new pattern is introduced. Tenant routing comes free:
`WorkspaceResolveMiddleware` gates membership and strips
`/api/w/{ws}/agents/…` to the flat path, pinning `request.workspace_slug`.

### Conventions (each verified against current code)

| Convention | Source |
|---|---|
| `Router(auth=session_auth, tags=["schedules"])`; PAT-bearing runners satisfy it via `BearerTokenAuthMiddleware` | `apps/harness/api.py` |
| Every route carries `summary=` and `openapi_extra={"x-mcp-expose": True}` | `apps/agents/api.py` |
| Lists return `Page[ScheduleOut]` via `apps.api.pagination.paginate`, `limit` clamped | `list_agents` |
| Creates use `response={201: ScheduleOut}` and return `Status` | `upsert_agent` |
| Schemas live in `apps/harness/schemas.py`, Pydantic v2, `model_validate` off the ORM | house rule |
| Errors via `ProblemError(status, title, type_=…)` → RFC 7807 `problem+json` | `apps/api/errors.py` |
| Agent resolution reuses `apps/agents/api.py::_get_agent_or_404` | see below |

### Auth + tenancy gate

Schedules **reuse `_get_agent_or_404`** rather than re-rolling the check. It does
three things that are easy to under-specify: `auto_join_workspaces(request.user)`,
then the `request.workspace_slug` tenant check, then `wsvc.is_member` — all three
failing to the *same* 404 as a missing agent, so tenancy never leaks existence.
(`Workspace` PK is the slug, so `agent.workspace_id != ws` compares slugs.)

### Cron validation

A Pydantic **field validator** on `ScheduleIn.cron` (and `timezone`) parses via
`croniter`/`zoneinfo`. Invalid input then 422s as real `problem+json` through the
existing `ValidationError` handler with no per-route code. This matters: a cron
typo that silently never fires is the worst failure mode a scheduler has, so it
must fail at edit time.

### Generated types

`npm run gen:api` regenerates `frontend/src/api/generated.ts`; the
`regen-openapi.yml` workflow auto-commits it on PRs touching `apps/**/api.py` or
`apps/**/schemas.py`. Frontend consumes via `openapi-fetch`.

## UI — a "Schedules" rail section

In the agent workspace (`/w/:workspace/agents/:slug`), built on `canopy-ui`,
dense table per house style (tables not cards, semantic tokens only — no
`stone-*`/`orange-*` literals):

| Schedule | When | Next | Last | |
|---|---|---|---|---|
| Weekly manager report | Fridays at 9:00 ET | in 2d | ✓ done | ⋯ |
| Goal review | 1st of month, 9:00 ET | in 11d | ⚠ missed | ⋯ |

Row actions: **Run now**, enable/disable toggle, edit.

Edit is a drawer with a friendly builder (freq / day / time / tz) over an
editable raw cron field, **live-previewing the next three fire times**. That
preview is what makes cron trustworthy without a docs trip.

## Testing

`uv run pytest`, focused on the invariants that actually bite:

- **Double-fire:** two runners, same slot → exactly one turn.
- **Supersede:** firing slot N+1 marks slot N's turn `missed`.
- **Grace release unwedges the agent:** a stale cron turn past `grace_minutes`
  must not block the next board turn. (Directly exercises the
  `one_executing_turn_per_agent` finding.)
- **No backfill:** three weeks of downtime → one turn, newest slot only.
- **DST:** 9am ET stays 9am across the shift.
- **Nag projection:** `needs_you` surfaces an unfinished schedule and clears once
  the turn is `done`.
- **Cron validation:** a bad expression 422s as `problem+json` at edit time.
- **Tenancy:** a non-member gets 404, not 403 (no existence leak).

## Open for iteration

Explicitly shipping thin to learn: grace period default (120m) and the
inbox-only nag are guesses. Both are single-field changes once there's real
usage.
