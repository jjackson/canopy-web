# Agent scheduled turns — design

**Date:** 2026-07-15
**Status:** Shipped (server + UI). Automatic firing awaits the runner-side
work — see *Runner-side work* in the plan; **Run now** is the only trigger today.
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
`agents.Agent`, never product apps).

**Int pk, not UUID** — unlike `Runner`/`Turn`/`SessionLink`. `AgentSchedule`
projects into the nag, and `NeedsYouItem.ref_id` is typed `int` on a
`StrictModel`, so a UUID would fail validation at the boundary. `AgentTask` — the
other object that projects there — is likewise int-pk'd. Runs already need a
`_run_ref_id()` cast to work around this; a second such hack isn't worth a UUID.

**No `workspace` FK.** A schedule is agent-owned, so it derives its tenant via
`agent.workspace`, exactly as `Turn` does. Commit 43f61ae states the rule: *"A
Turn derives its tenant via agent.workspace (no FK of its own)."* `Runner` needs
its own FK only because it is not agent-owned.

| Field | Type | Purpose |
|---|---|---|
| `id` | **int pk** (AutoField) | not UUID — see below |
| `agent` | FK `agents.Agent` | owner — **and the tenant, derived** |
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

**There is no FK from `Turn` to `AgentSchedule`** — the link is
`origin_ref["schedule_id"]`. That is what keeps the Turn the occurrence rather
than a child of one, but it means **nothing cascades on delete**, so deletion
needs an explicit rule:

> **Deleting a schedule supersedes its open occurrences first** (as `MISSED`,
> `result_note="schedule deleted"`), then deletes the row.

Both halves are load-bearing. An *executing* occurrence holds
`one_executing_turn_per_agent`, and `release_stale_occurrence_turns_all()`
resolves schedules by id — delete the row and that turn is permanently
unreleasable (the runner's heartbeat keeps renewing its lease, so the lease sweep
never rescues it either), wedging **every** subsequent turn for that agent
forever, with the nag that would have surfaced it deleted too. A *queued*
occurrence would otherwise outlive its schedule and later execute a prompt for a
schedule that no longer exists. Terminal occurrences are untouched: they are the
schedule's history, and the ledger outlives the declaration.

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

### Tenant scoping is mandatory on both runner-facing routes

`GET /api/harness/schedules/` and `POST /…/fire` **must** apply the runner's
tenant predicate — the same Q-based filter `claim_next_turn` and `list_turns`
use — and must **not** scope by `runner.agent_slugs()`.

This is not a hypothetical. Commit b4f5ead (`fix(harness): scope claim_next_turn
to the runner's tenant (Critical)`) records that `capabilities` is caller-supplied
at pairing and never validated: any authenticated user could pair a runner
declaring `capabilities={"agents": ["<victim-slug>"]}`, heartbeat it online, and
claim another tenant's turns. `capabilities` is a **routing hint**; the workspace
is the **security boundary**; the two intersect, never substitute.

A schedule-sync route scoped by capabilities would reopen exactly that hole, and
would leak `prompt` — the same field class b4f5ead called out. So:

The runner's tenant derives from **`paired_by`** — the human who paired it —
rather than a `Runner.workspace` field, for two reasons:

- `Runner.workspace` does not exist on `main`; it arrives with the concurrent
  canopy-mobile branch (`0004_runner_workspace`). Adding it here would collide
  with that migration for no gain.
- `paired_by` is server-assigned from `request.user` at pairing, so — unlike
  `capabilities` — it is not attacker-controlled. That is the entire point.

So a runner syncs/fires only schedules whose `agent.workspace` is one of
`paired_by`'s workspaces, plus null-workspace agents (the legacy pre-tenancy
path the existing suite covers). A runner with no `paired_by` gets an empty set.
When `Runner.workspace` lands this may narrow to it — the rule above is the
conservative superset, never a wider one. `_runner_or_404` and the harness-local
`_agent_or_404` provide the gate; 404 not 403, so non-membership never leaks
existence.

### Which runner fires — binding first, idempotency as backstop

Exclusivity is being moved to the **agent**, not the workspace: `AgentBinding`
(agent, runner, is_active) with a partial unique index, spec'd in 7765b71. It is
**not yet built** — the schedules work must not assume it exists.

Layered, so this is correct before *and* after binding lands:

1. **Once bound:** only one runner executes a given agent, so only one evaluates
   its schedules. No race to begin with.
2. **Until then (and for unbound agents):** both macOS-account runners may
   evaluate the same schedule and fire the same slot. Both produce an identical
   `idempotency_key`, and `enqueue_turn()` already treats that collision as a
   replay — it handles both the pre-check and the `IntegrityError` race.

Firing and claiming stay separate concerns: any capable in-tenant runner may
*fire* a slot; `claim_next_turn` alone decides who *executes* it, and that is
where binding applies. So a schedule never needs to know about bindings.

### No backfill

The runner fires only the **most recent** due slot. Laptop off for three weeks →
one goal review, not three. `last_slot` is the anchor.

## Supersede and release

Both happen server-side, and they are the same idea at two timescales — but they
run on **different ticks**:

- **Supersede:** inside the `fire` transaction. Firing slot N finds the
  schedule's prior non-terminal turn and calls
  `finish_turn(status=MISSED, result_note="superseded by <slot>")`. You only ever
  owe the newest occurrence. **Run now** supersedes on the same rule (it is the
  designed remediation for an unfinished slot, so it must retire the slot it
  remediates), and deleting a schedule supersedes too (see below).
- **Release:** on the **claim** tick, not the fire tick
  (`claim_next_turn` → `release_stale_occurrence_turns_all()`). An occurrence
  unattended past `grace_minutes` gets the same transition. This is what unwedges
  the agent, and a release here unblocks the very claim that triggered it. It
  cannot live on the fire tick: a weekly schedule's fire tick is 10,080 minutes
  apart and could never honour a 120-minute grace window.

**Supersede *is* the give-up.** The recurrence already defines the nag window — a
weekly report nags for a week, then next Friday supersedes it. No separate
"give up after N days" knob.

## The nag — a projection

`apps/agents/services.py::needs_you()` gains a source: for each enabled schedule,
if its latest turn is not `done`, emit a typed item (`ref_kind="schedule"`)
deep-linking to the agent's **Schedules** rail
(`/w/:workspace/agents/:slug/schedules`), where **Run now** lives. It lands in
the existing `waiting_count` badge the menu-bar runner panel already renders —
the surface Jonathan already looks at — with no new plumbing and no new model.

**Why a link, not an inline action.** `NeedsYouItem` has no `action` field —
every item in that projection carries a `url` and nothing else — so an inline
**Run now** button was never implementable without widening the shared inbox
contract for one item type. The deep-link delivers the same intent (the nag is
one click from the remedy) using the field every other builder already sets.
Widening `NeedsYouItem` with typed actions is open for iteration, and would be a
change to the inbox as a whole, not to schedules.

**This reaches every supervisor surface for free.** The fleet-wide
`GET /api/agents/needs-you` (ef11bda, on the canopy-mobile branch) is implemented
as `NeedsYouOut.model_validate(services.needs_you(a))` per agent — it *calls* the
per-agent function above. So hooking that one function puts the nag on
`/supervisor`, in `total_waiting` (the app-icon badge), and on the canopy-mobile
PWA, with no schedules-specific work on any of them. Hooking the per-agent
function rather than the fleet route is what buys this.

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
ad-hoc run never collides with a real slot and never advances `last_slot` — **the
cadence is unaffected**; the next real slot still fires on time.

It *does* **supersede** an open occurrence, exactly as `fire` does. Run now is the
remediation the nag points at, so the alternative is incoherent: the manual turn
would become the newest occurrence and clear the nag while the slot turn it was
meant to satisfy sat queued and still owed — then ran the work a second time when
a runner claimed it. You only ever owe the newest, however it was launched.

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
| Agent resolution reuses `apps/harness/api.py::_agent_or_404` | see below |

### Auth + tenancy gate

Schedules **reuse the harness-local `_agent_or_404`** (added in 43f61ae,
deliberately copied from `apps/agents/api.py:42` so the two are
indistinguishable) rather than re-rolling the check or importing across api
modules. It does three things that are easy to under-specify:
`auto_join_workspaces(request.user)`, then the `request.workspace_slug` tenant
check, then `wsvc.is_member` — all three failing to the *same* 404 as a missing
agent, so tenancy never leaks existence. (`Workspace` PK is the slug, so
`agent.workspace_id != ws` compares slugs.)

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
- **Cross-tenant runner sync (the b4f5ead regression test):** a runner paired
  with `capabilities={"agents": ["<victim-slug>"]}` but in another workspace must
  see **zero** schedules from `GET /harness/schedules/`, and its `fire` must 404
  — proving capabilities is not honored as a boundary and `prompt` never leaks.
  Model this on `tests/test_harness_authz.py`, which must actually heartbeat the
  runner before asserting (their commit message notes the old test never
  exercised the claim path at all).

## Concurrent work — canopy-mobile branch (`emdash/mobile-l2vmm`)

Reviewed 2026-07-15 while that branch was live. It is unmerged, so this spec is
written against `main` but must not fight it. Points of contact:

| Theirs | Effect here |
|---|---|
| `GET /agents/needs-you` fleet inbox (ef11bda) | **Free win** — calls per-agent `needs_you()`, so the nag reaches `/supervisor` + mobile with no extra work |
| `Runner.workspace` FK + membership gate (07a680e, 43f61ae) | Provides `_agent_or_404`/`_runner_or_404`; schedules reuse both |
| `claim_next_turn` tenant predicate (b4f5ead, Critical) | The rule the runner-facing schedule routes must mirror |
| `AgentBinding` — spec'd 7765b71, **not built** | Makes the fire race moot once landed; idempotency covers until then. Do not assume it exists |
| `NeedsYouItem.ref_kind` → `Literal` (2ce30c1) | On `main` it is still `str`, so `"schedule"` works today. **After merge, extend the Literal** to `["task", "sync", "work_product", "run", "schedule"]` or the nag 500s at serialization |
| harness migrations `0004`, `0005` | **Merge order:** they are not on `main`. If this lands second, renumber `AgentSchedule`'s migration to `0006_` and rebase. Both branches also touch `apps/harness/models.py` (they add `Runner.workspace`, we add `Turn.MISSED`) — a trivial but certain conflict |

## Open for iteration

Explicitly shipping thin to learn: grace period default (120m) and the
inbox-only nag are guesses. Both are single-field changes once there's real
usage.
