# DDD Run Views — design spec

**Date:** 2026-06-02
**Status:** Approved (implementing)
**Author:** Jonathan + Claude

## Problem

DDD (demo-driven-development) runs produce a coherent package of artifacts — a
hero **video**, an HTML **walkthrough/deck**, a **narrative** (the demo story
arc), and **links** (narrative / companion / reference). Today canopy-web has no
way to see them as a package:

- `Walkthrough` rows (`apps/walkthroughs/`) are a flat list. Each video and each
  HTML deck is an independent upload with no run grouping — the model has no
  `run_id`.
- `ReviewRequest` rows (`apps/reviews/`, shown at `/ddd-plans`) *do* carry a
  `run_id` (e.g. `microplans-2026-06-02-001`) plus the `narrative` /
  `narration[]`, but they point at a video only loosely via
  `request_json.video.walkthrough_id`.
- The canopy plugin treats a run as first-class in `run_state.yaml`
  (`run_id`, `feature`, `iteration_decks{}`, `iteration_clips{}`) but uploads
  each artifact independently to `POST /api/walkthroughs/`. The grouping never
  reaches the server.

We want a first-class **DDD** section: browse the **narratives** you're working
in → drill into a narrative's **runs** → open a run and see **everything**
(video, walkthrough, narrative, links). Modeled on ace-web's
opportunity→run→artifacts structure.

## Core concepts

- **Narrative** — the top-level grouping. A narrative is identified by the slug
  portion of `run_id`: strip the trailing `-YYYY-MM-DD-NNN` stamp.
  `microplans-2026-06-02-001` → narrative `microplans`. All `microplans-*` runs
  roll up to one narrative. The narrative's display title/story arc comes from
  the most recent `ReviewRequest` (for any run in the narrative) that has a
  `narrative` text.
- **Run** — one `run_id`. Aggregates its artifacts at read time.
- **Run package** — the video + deck + narrative + links + all-artifacts for a
  single run.
- **One-off uploads** — a `/canopy:walkthrough` share with no `run_id`. Still
  works, still mints URLs, still shows in the existing `/walkthroughs` list.
  Never appears in the DDD section.

## Decisions (locked)

1. **Grouping:** add `run_id` to `Walkthrough`; a run is a read-time aggregate
   joining `Walkthrough` + `ReviewRequest` on `run_id`. No new top-level model.
2. **Navigation:** new top-level **"DDD"** nav item, *alongside* the existing
   `Walkthroughs` and `DDD Plans` items (no removal/redirect in this change).
3. **IA:** persistent left nav (narratives, each expanding to its runs with a
   "previous runs" disclosure) + wide main area. Three URL levels.
4. **Run layout:** stacked, video first.
5. **Plugin change:** coordinated follow-up PR (separate repo). The API is
   backward-compatible; a backfill command bridges existing data.

## Data model

`apps/walkthroughs/models.py` — add three nullable fields to `Walkthrough`
(migration `0003`):

| Field | Type | Purpose |
|---|---|---|
| `run_id` | `CharField(max_length=255, null=True, blank=True, db_index=True)` | DDD run key, e.g. `microplans-2026-06-02-001`. The join key. Matches `ReviewRequest.run_id` length (255). |
| `feature` | `CharField(max_length=200, null=True, blank=True)` | Narrative slug sent by the plugin (matches `run_state.yaml`). Falls back to `feature_from_run_id(run_id)` when absent. |
| `role` | `CharField(max_length=20, null=True, blank=True)` | Artifact role: `hero_video` \| `deck` \| `docs` \| `clip`. When absent, derived from `kind` (`video`→`clip`, `html`→`deck`). |

Add a compound index `(run_id, -created_at)` to `Meta.indexes`.

No `role` choices enum enforced at the DB layer (kept open for plugin
evolution); the aggregator treats unknown/empty roles via the `kind` fallback.

### Shared helper

`feature_from_run_id(run_id: str) -> str` lives in a new
`apps/common/ddd.py` (or `apps/runs/aggregate.py`) and is imported by both
`apps/reviews` and `apps/runs`. It reuses the existing regex from
`apps/reviews/api.py`:

```python
_RUN_ID_STAMP = re.compile(r"-\d{4}-\d{2}-\d{2}-\d+$")

def feature_from_run_id(run_id: str) -> str:
    base = _RUN_ID_STAMP.sub("", run_id or "").strip("-")
    return base or run_id or "(untitled)"
```

`apps/reviews/api.py` is refactored to import this instead of its private
`_feature_from_run_id`, so the two apps agree on narrative identity.

## API — `apps/runs/` (new app)

A thin, **read-only** app: no models, just aggregation + a Ninja router +
schemas + a backfill management command. Mounted at `/api/ddd`.

Router auth: `session_auth` (same as walkthroughs/reviews — team-internal).

### Endpoints

- `GET /api/ddd/narratives/` → list narratives.
  Filters: `?project=<slug>`, `?mine=true` (walkthroughs owned by the user).
  Each item: `slug`, `title`, `phase` (best-effort from the newest
  ReviewRequest's gate/status), `run_count`, `latest_at`, `project_slug`,
  `has_video`, `has_deck`, `has_narrative`.
  Sorted by `latest_at` desc.

- `GET /api/ddd/narratives/{slug}/` → narrative landing.
  Returns `slug`, `title`, `story` (the narrative text from the latest
  ReviewRequest that has one), `phase`, plus `runs[]` — each run as
  `{run_id, created_at, latest_at, status, gate, scene_count, has_video,
  has_deck}` sorted newest first.

- `GET /api/ddd/runs/{run_id}/` → the run package. Fields:
  - `run_id`, `narrative_slug`, `created_at`, `latest_at`, `phase`
  - `video`: the chosen video artifact (or null) — `{id, title, content_url,
    duration_sec, share_token?}`. `content_url` is `/w/{id}/content` (+`?t=` when
    a share token is available to the requester).
  - `deck`: the chosen HTML artifact (or null) — same shape minus duration.
  - `narrative`: `{run_id, gate, title, story, narration[], personas, why_brief}`
    pulled from the chosen ReviewRequest, or null. Reuses the existing
    `ReviewRequestJson` shape (frontend already renders it).
  - `links[]`: union of `links` across the run's walkthroughs, de-duped by
    `(url, kind)`.
  - `all_artifacts[]`: every walkthrough in the run —
    `{id, title, kind, role, created_at}` (deep-link to `/w/{id}`).
  - `previous_runs[]`: other runs in the same narrative —
    `{run_id, latest_at}`, newest first, excluding the current run.

### Selection rules (pure function `build_run(run_id)`)

`build_run` is a pure function (queryset in, dict out) so it's unit-testable
without the HTTP layer.

- **video**: walkthroughs with this `run_id` and (`role == hero_video`) preferred,
  else (`role == clip`) , else `kind == video`. Pick most recent `created_at`.
- **deck**: `role == docs` preferred, else `role == deck`, else `kind == html`.
  Most recent.
- **narrative**: most recent `ReviewRequest` for this `run_id` whose
  `request_json` has a non-empty `narrative` or `narration`. If none has a
  narrative, fall back to the most recent ReviewRequest (for gate/phase) with a
  null story.
- **phase** (run + narrative level): derived from the newest ReviewRequest —
  `"{gate} · {status}"` (best-effort label, not a controlled vocabulary).
- **links**: concatenate `w.links` for all run walkthroughs; de-dupe on
  `(url, kind)`, preserving first occurrence order.

### Aggregation performance

Narrative list builds derived rows in Python from two small querysets
(`Walkthrough.objects.exclude(run_id__isnull=True/"")` and `ReviewRequest`),
mirroring the existing reviews-dashboard approach (team-internal, small N).
Group by `feature_from_run_id`. No N+1 concerns at current scale; revisit if the
set grows.

### Schemas

`apps/runs/schemas.py` — `NarrativeListItemOut`, `NarrativeDetailOut`,
`RunArtifactOut`, `RunNarrativeOut`, `RunPackageOut`, etc., all `StrictModel`
subclasses. The narration/persona/why-brief sub-shapes are reused from the
review payload (typed loosely as needed since they live inside `request_json`).

## Upload contract change (`apps/walkthroughs/api.py`)

`upload_walkthrough` accepts three new **optional** form fields:
`run_id: str = Form("")`, `feature: str = Form("")`, `role: str = Form("")`.
Stored on the row (empty → null; `feature` defaults to
`feature_from_run_id(run_id)` when `run_id` is present but `feature` is blank).
`WalkthroughDetailOut` / `WalkthroughListItemOut` gain optional `run_id`,
`feature`, `role` fields so the existing viewer/list can show run linkage. The
endpoint stays backward-compatible (all new fields optional).

## Backfill — `manage.py backfill_run_ids`

A management command (`apps/runs/management/commands/backfill_run_ids.py`) that
populates `run_id`/`feature` on existing walkthroughs:

1. **Authoritative:** for every `ReviewRequest`, read
   `request_json.video.walkthrough_id`; if it resolves to a walkthrough with no
   `run_id`, set `run_id = review.run_id`, `feature = feature_from_run_id(...)`.
2. **Fallback (heuristic, opt-in via `--from-titles`):** match walkthroughs
   whose `title` begins with a known narrative slug. Logged, not silent.

Idempotent; `--dry-run` prints what it would change. Never overwrites a non-null
`run_id`.

## Frontend

### Routes (`frontend/src/router.tsx`)

```
/ddd                       → DddPage (home: left nav, empty main)
/ddd/:narrative            → DddPage (narrative landing in main)
/ddd/:narrative/:runId     → DddPage (run package in main)
```

A single `DddPage` owns the persistent left nav and swaps main content by
route params (like ace-web's workbench keeping the sidebar persistent). Nav item
**"DDD"** added to `NAV_ITEMS` in `AppLayout.tsx` (after "DDD Plans").

### Components (`frontend/src/pages/Ddd/` + `frontend/src/components/ddd/`)

- `DddPage.tsx` — layout shell: left nav + `<Outlet>`-style main switch on params.
- `DddLeftNav.tsx` — lists narratives; the active narrative expands to its runs
  (latest marked ●; older under `▸ previous runs (n)`). Project filter +
  "mine only" toggle at top. Stone-dark + orange theme (PR #76).
- `NarrativeLanding.tsx` — narrative title + story arc + runs as cards
  (date · status · has-video/deck chips).
- `RunPackage.tsx` — stacked: header (narrative · run_id · phase · created) →
  `RunVideo` → `RunDeck` → `RunNarrative` → `RunLinks` → `AllArtifacts`.
  - `RunVideo` — `<video controls>` from `content_url`, or empty state.
  - `RunDeck` — sandboxed `<iframe>` (reuse `walkthroughContentUrl` pattern), or
    empty state.
  - `RunNarrative` — renders story arc + per-scene narration (reuse the review
    page's narration rendering where practical), or "no narrative yet".
  - `RunLinks` — grouped narrative / companion / reference (reuse the viewer's
    link grouping from `WalkthroughViewerPage`).
  - `AllArtifacts` — strip listing every upload with deep links to `/w/:id`.

### API client + types

`frontend/src/api/ddd.ts` — `listNarratives(filters)`, `getNarrative(slug)`,
`getRun(runId)`. Follows the same raw-fetch + CSRF convention as
`frontend/src/api/reviews.ts` (the runs endpoints won't be in generated types
initially; regenerate `generated.ts` via `npm run gen:api` once the backend is
in so they can migrate to `openapi-fetch` later).

## Testing

- `apps/runs/tests/test_aggregate.py` — `build_run` selection (video/deck/
  narrative precedence), link de-dup, previous-runs grouping, missing-artifact
  cases; `feature_from_run_id` edge cases.
- `apps/runs/tests/test_api.py` — narratives list (+filters +auth), narrative
  detail, run package; 404/empty behavior.
- `apps/runs/tests/test_backfill.py` — backfill via review linkage + dry-run +
  idempotency.
- `apps/walkthroughs/tests/` — upload accepts/stores new fields; detail exposes
  them.
- Frontend: `npm run build` (type-check) + manual dogfood of `/ddd` via browse
  against seeded data.

## Out of scope

- Per-run share token / "share the whole run" surface (artifacts keep their own
  tokens). Tracked for a follow-up.
- Removing or redirecting the existing `Walkthroughs` / `DDD Plans` nav items.
- Editing run metadata from the DDD UI (read-only views).
- The plugin-side `upload.py` / `promote.py` change (coordinated follow-up PR in
  the canopy plugin repo).
