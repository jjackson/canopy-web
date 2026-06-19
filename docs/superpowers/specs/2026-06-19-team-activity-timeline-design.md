# Team Activity Timeline — Design Spec

**Date:** 2026-06-19
**Status:** Approved (brainstorm) → ready for implementation plan
**Scope:** One spec. Link-out only. In-panel rendering and object-URL standardization are explicitly deferred.

## Problem

Work now happens in parallel across many subsystems — DDD runs, narrative
reviews, insights, walkthroughs, shareouts, agent syncs, sessions, project
context. There is no single place to see "what has been completed recently"
across the whole workspace. Today you must visit `/ddd`, `/insights`,
`/shareouts`, `/agents/:slug`, etc. one at a time to reconstruct a mental
timeline.

## Goal

A single `/timeline` page: a reverse-chronological, team-wide activity feed
across **every** subsystem, **filterable** down to one subsystem so you can see
just that subsystem's timeline. Each row links out to the object's real URL.
Read-only.

## Non-goals (deferred)

- **In-panel object rendering** — selecting a row does not render the object in
  a main panel; it navigates to the object's existing page.
- **Renderer registry / embeddable detail components** — not built. No consumer
  exists yet; designing the embedding contract before the panel UI exists would
  guess the contract wrong.
- **Canonical `/o/<type>/<id>` URLs / workbench URL standardization** — not
  built. There is exactly one link generator (the aggregator), so retrofitting
  to a canonical address layer later is cheap. Each event preserves explicit
  identity (`subsystem` + `kind` + `id`) so that layer can be introduced
  **non-destructively** in a future spec without re-instrumenting adapters.

## Architecture

### Read-time aggregator (no new tables, no backfill, no write instrumentation)

A new `apps/timeline/` Django app exposes one endpoint. It does **not** own
models. It holds a **registry** of per-subsystem "source" functions. Each
participating app owns a small `timeline.py` exporting:

```python
def recent_events(*, limit: int, before: datetime | None, user) -> list[ActivityEvent]: ...
```

This keeps each subsystem's event-mapping knowledge inside that subsystem's app
(no cross-app model reaching from the aggregator) and makes adding a subsystem a
one-file change plus one registry line.

The endpoint:

```
GET /api/timeline/?subsystem=<key>&limit=<n>&before=<iso8601>
```

1. Resolve the set of sources: all registered, or just `subsystem` if given.
2. Call each source with `limit` + `before` (so each returns at most `limit`
   rows newer than the cursor — bounds the work per source).
3. Merge, sort by `at` descending, slice to `limit`.
4. Return events + the subsystem catalog + the next cursor.

Default `limit` = 50 (team-wide stream is busier than a single subsystem).
Sources are bounded by `limit`, so worst-case work is `len(sources) * limit`
rows fetched then merged — fine for a "recent" window. A written activity-log
table can replace the aggregator later if deep pagination is ever needed; the
endpoint contract would not change.

### Event shape

`apps/timeline/schemas.py`:

```python
class ActivityEventOut(Schema):
    subsystem: str          # filter key: "ddd" | "insights" | "walkthroughs" | ...
    kind: str               # verb within subsystem: "run" | "narrative_review" | "insight" | "shareout" | "sync" | "work_product" | "task" | "session" | "context" | "skill" | "workspace"
    at: datetime            # sort timestamp
    title: str              # headline (e.g. narrative title, insight one-liner)
    summary: str | None     # one supporting line
    project_slug: str | None
    actor: str | None       # owner display name/email, if known
    href: str               # real in-app URL to open (or external URL for work products)
    external: bool = False  # true → open in new tab (e.g. AgentWorkProduct.url)
    icon: str | None         # chip hint for the frontend (e.g. "video", "deck", "doc")
    id: str                 # stable id for React keys + future canonical addressing
```

`ActivityEvent` is a plain dataclass internally (what sources return);
`ActivityEventOut` is the Ninja/Pydantic response schema. The list endpoint
returns:

```python
class TimelineOut(Schema):
    events: list[ActivityEventOut]
    subsystems: list[SubsystemOut]   # [{key, label}] catalog for the rail
    next_before: datetime | None     # cursor for "show more"; null when exhausted
```

### Cursor pagination

`before` is the `at` of the last event already shown. Each source filters
`<ts> < before`; the merged result's last `at` becomes `next_before`. `null`
when fewer than `limit` events come back.

## Subsystem catalog

Each subsystem is a filter key. "All" (no `subsystem` param) merges every
source. Visibility-gated sources (walkthroughs, reviews, sessions) honor their
`visibility` field against the requesting user.

| Subsystem (`key`) | Label | Source model(s) | Sort ts | Link-out href |
|---|---|---|---|---|
| `ddd` | DDD | runs (Walkthrough grouped by `run_id`, via `apps/runs/aggregate.py`) + narrative `ReviewRequest` (narrative gates only) | run `latest_at`; review `resolved_at` or `created_at` | run → `/ddd/{narrative}/{runId}`; review → `/review/{id}` |
| `insights` | Insights | `ProjectContext` where `context_type="insight"` | `created_at` | `/insights` |
| `walkthroughs` | Walkthroughs | standalone `Walkthrough` (no `narrative_slug`) | `created_at` | `/w/{id}` |
| `shareouts` | Shareouts | `Shareout` | `period_end` | `/shareouts/{period}` |
| `agents` | Agents | `AgentSync` + `AgentWorkProduct` + `AgentTask` | sync `period_end`; others `created_at` | sync → `/agents/{slug}/syncs`; work_product → `url` (external); task → `/agents/{slug}/tasks` |
| `sessions` | Sessions | `Session` | `created_at` | `/share/{token}` if `visibility="link"`, else `/sessions` |
| `projects` | Projects | `ProjectContext` (non-insight types) + `ProjectAction` | context `created_at`; action `started_at` | `/` (workbench) |
| `skills` | Skills | `Skill` | `created_at` | `/skills/{id}` |
| `workspace` | Workspace | `WorkspaceSession` (status `published`) | `updated_at` | `/workspace/{id}` |

**DDD source** reuses the existing read-time join in `apps/runs/aggregate.py`.
Runs and narrative reviews are two `kind`s under the one `ddd` subsystem.
Non-narrative review gates (`external_release`, `product_findings`) are excluded
(already filtered by `_NON_NARRATIVE_GATES` in aggregate).

**Walkthroughs vs DDD:** a `Walkthrough` with a `narrative_slug`/`run_id`
belongs to a DDD run and is surfaced via the `ddd` source. The `walkthroughs`
source only emits standalone uploads (`narrative_slug` is null) to avoid double
counting.

## Frontend: `/timeline`

- New route `/timeline` in `frontend/src/router.tsx` + a top-nav entry.
- `frontend/src/pages/TimelinePage.tsx` uses the `@canopy/workbench` shell (same
  chrome as DDD/Agents):
  - **Left rail:** "All activity" + one entry per subsystem from the returned
    catalog. Single-select. Selecting sets `?subsystem=<key>` in the URL so a
    filtered view is a shareable link. `/timeline` (no param) = All.
  - **Main:** dense vertical feed grouped by day (Today / Yesterday / `MMM D`).
    Each row: relative time · subsystem chip · project badge (if `project_slug`)
    · `title` · `summary` · `actor`. Whole row navigates to `href` (internal →
    router navigation; `external` → `window.open`/`target=_blank`).
  - **Show more:** appends the next page using `next_before`; hides when null.
- `frontend/src/api/timeline.ts`: `listTimeline({ subsystem?, limit?, before? })`
  returning the typed `TimelineOut`, following the existing `frontend/src/api/ddd.ts`
  fetch-wrapper pattern (`credentials: 'same-origin'`).
- Styling: semantic tokens only (`bg-card`, `border-border`, `text-foreground`,
  `text-muted-foreground`, `text-primary`). Table-dense, no card soup.

## Auth & visibility

- Endpoint is session-authed (`session_auth`), like the rest of the API; also
  PAT-resolvable via the bearer middleware.
- Each source filters by the requesting user where the model is owner- or
  visibility-scoped:
  - `Walkthrough` / `ReviewRequest` / `Session`: include if `visibility="link"`
    OR `owner == user`.
  - Owner-scoped-only models (e.g. `Session` private) excluded for non-owners.
- Org-wide models (projects, insights, shareouts, skills) are visible to any
  authenticated user (single-tenant V1, consistent with existing endpoints).

## Testing

- **Per-source unit tests** (`apps/timeline/tests/` or each app's tests): given
  fixture rows, `recent_events` returns correctly-shaped, correctly-ordered,
  visibility-filtered events with resolving hrefs.
- **Endpoint tests:** merge ordering across sources; `subsystem` filter
  restricts to one source; `before` cursor paginates; `limit` honored;
  anonymous/cross-user visibility filtering; empty state.
- **Frontend:** `npm run build` type-checks against regenerated OpenAPI types.

## Files

**Backend (new):**
- `apps/timeline/__init__.py`, `apps/timeline/api.py`, `apps/timeline/schemas.py`,
  `apps/timeline/sources.py` (registry + merge/sort/slice), `apps/timeline/types.py`
  (the `ActivityEvent` dataclass), `apps/timeline/tests/`.

**Backend (one small file per participating app):**
- `apps/projects/timeline.py` (insights + projects sources)
- `apps/walkthroughs/timeline.py`
- `apps/shareouts/timeline.py`
- `apps/agents/timeline.py`
- `apps/sessions/timeline.py`
- `apps/skills/timeline.py`
- `apps/workspace/timeline.py`
- `apps/runs/timeline.py` (DDD runs + narrative reviews; reuses `aggregate.py`)

**Backend (edit):**
- `apps/api/api.py` — register `api.add_router("/timeline", timeline_router)`.
- `config/settings/*` — add `apps.timeline` to `INSTALLED_APPS` if app config is
  required (no models, so may not be necessary; include for discoverability).

**Frontend (new):**
- `frontend/src/api/timeline.ts`, `frontend/src/pages/TimelinePage.tsx`,
  timeline row/rail components under `frontend/src/components/timeline/`.

**Frontend (edit):**
- `frontend/src/router.tsx` — add `/timeline` route.
- top-nav component — add the Timeline entry.
- `frontend/src/api/generated.ts` — regenerated from OpenAPI.

## Rollout

Additive. No migrations (read-time aggregator, no new tables). No changes to
existing endpoints. Ships behind no flag; the page is simply a new route.
