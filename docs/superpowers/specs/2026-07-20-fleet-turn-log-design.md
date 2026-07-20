# Fleet Turn Log — design

**Date:** 2026-07-20
**Status:** Approved (pending spec review)

## Problem

Every triggered agent turn is already recorded in the harness `Turn` ledger —
its trigger (`origin`: cron / manual / email / api), which runner ran it
(`claimed_by`), its status, and its timestamps. `GET /api/harness/turns/`
returns all of this, tenant-scoped. But there is **no browsable page** that
answers the plain operational question: *"what fired recently, what triggered
it, which runner ran it, and did it succeed?"* Today you answer it with an API
call or by opening each agent's rail. This spec adds a single read-only fleet
**Activity** view.

Framing: **Schedules = what will fire; Activity = what did fire.** The Activity
page is the exact sibling of the existing `/schedules` calendar.

## Scope

One read-only frontend page over one existing endpoint, plus a one-line
backend addition (a `limit` query param). Explicitly **not** in scope:
- No new model, migration, or write path.
- No pagination / "load more" — the view shows the last 20 turns. (100 was
  offered and rejected as more than useful.)
- No live polling / websockets — a manual refresh + refetch-on-mount is enough.

## Route + placement

- `/activity` — personal, fleet-wide: every turn across all workspaces the
  caller belongs to.
- `/w/:workspace/activity` — the same view pinned to one tenant.

One `ActivityPage` component mounts both routes, mirroring how `SchedulesPage`
mounts `/schedules` and `/w/:workspace/schedules`. A nav entry sits next to
Schedules. Both are personal/global-or-tenant surfaces, not part of the agent
rail.

Tenancy is already handled by the endpoint + `WorkspaceResolveMiddleware`:
under `/w/{ws}/` the middleware pins `request.workspace_slug`; flat calls read
`None` and fall back to all the caller's workspaces. The frontend `apiV2`
client already rewrites flat `/api/harness/...` → `/api/w/{ws}/harness/...`
when mounted under a tenant route (`WS_SCOPED_API_PREFIXES`), so the component
does not special-case the workspace itself.

## Backend change

`apps/harness/api.py::list_turns` currently returns `list(qs[:100])`. Add an
optional `limit`:

```python
@router.get("/turns/", response=list[TurnOut])
def list_turns(request, agent=None, status=None, limit: int = 100):
    ...
    limit = max(1, min(limit, 200))   # clamp; default preserves existing callers
    return list(qs[:limit])
```

- Default stays `100` so every existing caller (runner, tests, MCP) is
  unchanged.
- Clamped to `1..200` so a caller can neither ask for `0`/negative nor pull an
  unbounded slice.
- The page requests `?limit=20`.

Ordering (`-created_at`), tenant filter, and the `agent`/`status` filters are
untouched.

No schema change: `TurnOut` already exposes `id, agent_slug, project, target,
workspace_slug, origin, status, routing, prompt, origin_ref, claimed_by_name,
enqueued_by_email, session_id, result_note, created_at, claimed_at,
started_at, finished_at, lease_expires_at`.

## The page

A dense, newest-first table (tables-not-cards, per house style). Columns:

| Column | Source | Rendering |
|--------|--------|-----------|
| **Time** | `created_at` | Relative ("2h ago"); absolute Mountain Time on hover (`title`) |
| **Agent** | `agent_slug`, else `project` | Agent slug; project turns render `project:<name>` |
| **Trigger** | `origin` (+ `origin_ref`, `enqueued_by_email`) | Chip: `cron` shows the fired slot from `origin_ref`; `manual` shows `enqueued_by_email`; `email` / `api` as-is |
| **Runner** | `claimed_by_name` | Runner name, or `—` if never claimed |
| **Status** | `status` | Colored chip: queued / claimed / running / done / failed / missed |

Status colors map to existing semantic status tokens (`success` = done,
`destructive` = failed, `warning` = missed, `info`/muted = queued/claimed/
running) — no palette literals. Both light and dark themes via the token set.

### Filters

Three client-side filter controls over the fetched set — **agent**, **origin**,
**status** — each a dropdown/chip row whose options are derived from the turns
actually present. A pure predicate `matchesTurnFilters(turn, filters)` decides
row visibility, mirroring the calendar's `matchesFilters`. Filtering never
refetches; it's pure display over the last-20 payload.

### Row drill-down

Clicking a row expands it inline to show that turn's **event ledger** —
`GET /api/harness/turns/{id}/events` — rendered as a compact ordered list
(`seq · kind · message/at`). The ledger is the append-only record of what
happened inside the turn (claimed → started → tool calls → finished). Fetched
lazily on first expand and cached per-row in component state, so re-collapsing
and re-expanding costs nothing and only expanded rows ever hit the events
endpoint.

### States

- **Loading:** a lightweight skeleton (rows), not a spinner-only blank.
- **Empty:** "No turns yet." with a one-line hint that turns appear here once an
  agent is triggered (by a schedule, email, or a manual run).
- **Error:** the shared error surface used by other list pages (the RFC 7807
  `detail`), with a retry.

## Testing

**Backend (pytest, `tests/test_harness_api.py` — the module already covering
`list_turns`):**
- `limit` clamps: `?limit=0` → 1 row max, `?limit=9999` → ≤200, `?limit=20` →
  ≤20, omitted → ≤100 (default preserved).
- Existing `agent` / `status` / tenant-scope tests remain green (the param is
  additive).

**Frontend (vitest, pure functions only — no `@testing-library`, per house
rule):**
- `originLabel(turn)` — cron→slot string, manual→email, email/api passthrough.
- `matchesTurnFilters(turn, filters)` — agent/origin/status predicate, incl.
  the "no filter = everything" identity and multi-filter AND.
- `relativeTime(from, now)` — a fixed `now` in, deterministic string out (no
  wall-clock dependence).

## Files

- `apps/harness/api.py` — add `limit` param to `list_turns` (~2 lines).
- `tests/test_harness_api.py` — `limit` clamp/default test.
- `frontend/src/router.tsx` — two routes (`/activity`, `/w/:workspace/activity`).
- `frontend/src/pages/ActivityPage.tsx` — the page (table + filters + row expand).
- `frontend/src/components/activity/turnLog.ts` — pure helpers (`originLabel`,
  `matchesTurnFilters`, `relativeTime`, status→token map).
- `frontend/src/components/activity/turnLog.test.ts` — vitest for the helpers.
- `frontend/src/components/AppLayout/AppLayout.tsx` — add the Activity nav entry
  (`{ path: '/activity', label: 'Activity', tenant: false }`) next to Schedule.

## Non-goals / deferred

- Pagination / infinite history (last-20 is the whole ask).
- Live updates.
- Turn-level actions (retry / cancel) — this is a read-only log.
- A per-agent Activity rail section — the fleet + tenant views cover the need;
  the per-agent Turns rail (`AgentTurnsSection`, packaged reports) already
  exists and is a different thing (curated deliverables, not the raw ledger).
