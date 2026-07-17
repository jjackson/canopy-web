# Fleet schedule calendar — design

**Date:** 2026-07-16
**Status:** Approved, not yet implemented
**Tier:** Framework (`apps/harness` + `canopy_cron` + frontend)

## Problem

Schedules are visible only one agent at a time (`/w/:ws/agents/:slug/schedules`).
To see "what's my week look like across the fleet" you click into each agent in
each workspace. There is no roll-up. The ask: a **weekly calendar** of every
recurring activity, at two scopes — **per workspace** and a **personal**
roll-up spanning every workspace you belong to — with **filters** by workspace
and agent.

## The shape in one sentence

**One grid component, mounted at two routes, backed by one endpoint** whose
scope is decided entirely by whether the URL is tenant-pinned — so the personal
view genuinely *is* the workspace view with the pin removed, not a second code
path.

## Backend

### 1. Window-based fire calculation — `canopy_cron.slots_between`

The grid needs every fire in the visible week. `next_slots` returns only the
next N; a daily schedule alone is 7 in a week. Add to the shared library
(`packages/canopy_cron`), so the server computes fires the same way the runner
fires them — the same reason `next_slots`/`due_slot` already live there:

```python
def slots_between(cron: str, tz: str, start: datetime, end: datetime) -> list[datetime]:
    """Every fire time in [start, end) — half-open. Returns tz-aware UTC instants,
    ordered. start/end are tz-aware; the cron is evaluated in `tz`."""
```

Half-open `[start, end)` so adjacent weeks tile without double-counting a fire
that lands exactly on a boundary. Tested for: empty week, a daily cron → 7, the
inclusive-start/exclusive-end boundary, and a DST-crossing week (a 9am-local
fire stays 9am-local across the shift — the property `due_slot` is already
tested for, applied to a window).

### 2. The week endpoint — `GET /api/agents/schedules/week?start=<iso>`

Returns every **enabled** schedule the caller can see, each with its
`ScheduleOut` shape **plus** `workspace_slug` **plus** its fires in
`[start, start+7d)`.

**Scope is the URL, not a parameter.** The route mounts once on the agents
namespace (beside the existing schedule routes). `WorkspaceResolveMiddleware`
already strips `/api/w/{ws}/…` to the flat path and sets
`request.workspace_slug`, so:

- `GET /api/agents/schedules/week` (flat) → **personal roll-up**: every
  workspace the caller is a member of.
- `GET /api/w/{ws}/agents/schedules/week` (pinned) → **that workspace only**.

Both resolve the visible-workspace set the **same way** `_visible_agent_workspace_ids`
(`apps/agents/api.py`) does — pinned → `{ws}`; unpinned → every membership +
`None` for legacy unhomed agents — but built directly from `apps.workspaces.services`
primitives (`auto_join_workspaces`, `user_workspace_slugs`), **not** by importing
that helper. Harness api modules must not depend on the agents api module — the
same rule that forced `_agent_or_404` to be duplicated in harness rather than
imported. Building from the shared `wsvc` primitives keeps the boundary identical
without the illegal cross-import.

> **Optional cleanup for the plan/reviewer to weigh:** the "which workspace ids
> can this user see" predicate is fundamentally a `wsvc` concern and is now
> expressed in three places (`_visible_agent_workspace_ids`, `_runner_visibility_q`,
> and here). Promoting it to `apps/workspaces/services.py::visible_workspace_ids(user, pinned)`
> so all three call one definition would be the DRY fix — but it touches audited
> security code in two other apps, so it is a judgment call, not required by this
> feature.

**Declared BEFORE the `/{slug}/schedules/…` routes** so "schedules/week" isn't
resolved as `slug="schedules"` — the same ordering `needs-you` relies on.

Response schema (`ScheduleWeekOut`):

```python
class ScheduledFireOut(Schema):
    schedule: ScheduleOut       # full shape — a chip carries everything the editor needs
    workspace_slug: str | None
    fires: list[datetime]       # UTC instants in the window

class ScheduleWeekOut(Schema):
    start: datetime
    items: list[ScheduledFireOut]
```

Returning the full `ScheduleOut` per item (not just id+time) is deliberate: the
grid's edit popover opens the existing `ScheduleEditor` with no second fetch.

## Timezone — one clock across the whole grid

Each schedule carries its own IANA tz. On a fleet grid spanning workspaces,
rendering each fire in its *own* tz would make the columns lie. So: **the server
returns absolute UTC instants; the client places every fire on the grid in the
viewer's local tz.** One clock. The tz is labeled once in the header
("times in America/New_York"). A "Friday 9am Tokyo" schedule correctly shows at
the viewer's Thursday-evening slot — because that's when it actually fires for
you. The grid answers "when do things happen," not "what does each agent think
its local time is."

## Frontend

### One grid, two routes

- **`/schedules`** — root, personal, spans every workspace you belong to.
  Sibling to `/insights` and `/supervisor`, root-mounted for the same stated
  reason (the fleet spans workspaces; `CLAUDE.md` §Key URLs). Header nav link.
- **`/w/:workspace/schedules`** — tenant, that workspace only. Fits the `/w/`
  tenant URL scheme like every other tenant surface.

Both mount the same `<ScheduleCalendar>`; the route decides which API path it
calls (flat vs `/w/{ws}/`). The tenant route hides the workspace filter (it is
already one workspace).

### The grid — day columns of chips

7 columns (Mon–Sun of the visible week), each a time-ordered list of **fire
chips**. A chip = time · agent · schedule name, tinted by agent. A fire is an
instant (a turn kicks off), not a span, so there is no hour ruler and no overlap
math — same-time fires simply stack in order. Prev / This week / Next
navigation; "This week" is the default landing.

**"Show paused" toggle** — disabled schedules have no fires, so they are hidden
by default; the toggle renders them as ghost chips at their *would-be* times so
you can see and re-enable them.

### Filters (client-side)

The week's fires across a person's schedules is a small, bounded set, so the
grid fetches once and filters in memory — instant, no backend params:

- **By agent** — both views.
- **By workspace** — personal view only (the tenant view is already scoped).

Filter chips sit above the grid; workspace chips double as the color key.

### Edit — the existing `ScheduleEditor`, reused (the DRY constraint)

`frontend/src/components/agents/ScheduleEditor.tsx` is already a self-contained,
agent-agnostic modal: `{agentSlug, schedule, onClose, onSaved}`. The per-agent
Schedules page mounts it today; the calendar mounts the **same component** in a
popover on chip-click, passing the chip's `agentSlug` + `Schedule`. Full
edit / pause / run-now / delete, inline, from one editor — **zero new mutation
UI**. On `onSaved`/close, the grid refetches the week. This satisfies "both pages
use the same edit UI" by reuse, not reimplementation; no refactor of the
per-agent page is required.

## Testing

- `slots_between` — unit tests in `canopy_cron`'s suite (window boundaries, empty
  week, daily→7, DST-crossing week).
- The week endpoint — cross-workspace scoping test mirroring `fleet_needs_you`'s:
  a caller in workspaces A and B sees agents in A and B; an agent in workspace C
  (not a member) never appears; the tenant-pinned URL returns only that
  workspace. Non-member → no leak.
- Frontend — typecheck (`npm run build`) + vitest on the pure helpers
  (day-bucketing a fire list into columns; the agent/workspace filter predicate),
  per the repo's frontend convention (pure functions only; no `@testing-library`).

## Non-goals (YAGNI)

- Month view, drag-to-reschedule, the hour-ruled or heatmap layouts (the
  brainstorm rejected these against "see the overall schedule").
- Server-side filtering / pagination of the week (the fire set is small).
- Any new mutation surface (the shared editor is the whole write path).

## Files

| File | Change |
|---|---|
| `packages/canopy_cron/canopy_cron/slots.py` | **add** `slots_between` |
| `packages/canopy_cron/tests/…` | window + DST tests |
| `apps/harness/api_schedules.py` | **add** the `/schedules/week` route (before `/{slug}/`) |
| `apps/harness/schedule_services.py` | **add** `week_schedules(workspace_ids, start)` — the request-free aggregator; the route passes the resolved `wsvc`-derived workspace-id set so the service imports no api module |
| `apps/harness/schemas.py` | `ScheduledFireOut`, `ScheduleWeekOut` |
| `tests/test_schedule_week.py` | endpoint scoping + shape |
| `frontend/src/api/schedules.ts` | `getScheduleWeek(start, workspaceSlug?)` |
| `frontend/src/components/schedules/ScheduleCalendar.tsx` | **new** — the grid + popover |
| `frontend/src/components/schedules/calendarGrid.ts` (+ `.test.ts`) | **new** — pure day-bucketing + filter helpers |
| `frontend/src/pages/SchedulesPage.tsx` | **new** — mounts the grid at both routes |
| `frontend/src/router.tsx` | `/schedules` + `/w/:workspace/schedules` |
| `frontend/src/components/layout/…` | header nav link |
| `CLAUDE.md` | the two routes + the endpoint |

## Decided: the aggregator lives in the service layer

`week_schedules` goes in `apps/harness/schedule_services.py`, not inline in the
route — consistent with the schedule CRUD extraction, and so a future MCP `week`
tool is a thin wrapper over the same function. The route stays a thin adapter:
resolve the visible-workspace set, call the service, serialize. The service
takes the resolved workspace ids (the route computes them from
`_visible_agent_workspace_ids`), so the service itself stays request-free and
does not import the api module.
