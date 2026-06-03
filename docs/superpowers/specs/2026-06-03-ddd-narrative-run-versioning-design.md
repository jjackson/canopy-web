# DDD Narrative / Run / Version model — design spec

**Date:** 2026-06-03
**Status:** Draft for review (not yet implementing)
**Author:** Jonathan + Claude
**Supersedes the grouping model in:** `2026-06-02-ddd-run-views-design.md`

## Problem

The first cut of `/ddd` groups artifacts by `run_id` and treats a run's
narrative as "the `ReviewRequest` that shares the same `run_id`." Live data
exposed two faults this model can't represent:

1. **Runs aren't immutable.** The orchestrator *resumed* one run_id
   (`did-monitoring-2026-06-01-001`) and iterated in place across days. Each
   `ddd-upload` invocation **appends** a fresh hero-video + docs (no dedup), so
   that one run accumulated **9 artifacts** — including two byte-identical
   re-uploads (verified by sha256: the 20:48 video == the 17:52 video; the
   03:12 "N1" video == the 03:11 video).
2. **The narrative has no identity of its own.** A "redraft" just re-posts a
   `ReviewRequest` under the same `run_id`, silently superseding the prior one.
   There is no way to see that the *story* evolved, or which story a given run
   actually rendered.

Root cause: `run_id` is being asked to mean three different things at once — the
narrative, a story revision, and an execution. They need to be separate.

## Target model (three levels)

```
Narrative  (stable narrative_id, e.g. "did-monitoring")   ← the thing you're demoing
├─ Narrative versions  (the story/spec, iterated over time: v1, v2, …)
│     each is editable + viewable; the latest is "current"
└─ Runs  (each a DDD loop render; fresh run_id; IMMUTABLE artifact set)
      did-monitoring-2026-06-03-001  → video + deck + links
        └─ rendered_from: narrative version v2
      did-monitoring-2026-06-03-002  → …
        └─ rendered_from: narrative version v2
```

Two things iterate **independently** under a narrative:
- **Narrative versions** — the story changes (re-draft, scene edits). Versioned,
  with history; each version is a `ReviewRequest` (the editable surface).
- **Runs** — each DDD loop render mints a **fresh** `run_id`, produces one
  **immutable** artifact set, and **records which narrative version it
  rendered**. Re-rendering is a *new run*, never an in-place append.

`/ddd` navigation becomes:
- **L1 Narratives** — list (title, run count, latest activity, current phase).
- **L2 Narrative** — current story + **version history** (+ edit link to the
  review) **and** the list of runs (newest first).
- **L3 Run** — the frozen package (video + deck + links) **+ the narrative
  version it was built from** (+ edit link to that version).

## Identity & relationships

| Concept | Stable id | Notes |
|---|---|---|
| Narrative | `narrative_id` = the `feature` slug (e.g. `did-monitoring`) | Already the explicit field the plugin sends. Stays the stable anchor. |
| Narrative version | `(narrative_id, version)` — a `ReviewRequest` | Versioned story. `version` is a monotonic int per narrative. |
| Run | `run_id` (e.g. `did-monitoring-2026-06-03-001`) | Immutable artifact set. References the narrative version it rendered. |

**The decoupling (the core change):** today the run↔narrative join key is
`run_id`. In the target model:
- A **narrative version** (`ReviewRequest`) is keyed by `narrative_id` (+
  `version`), **not** a run_id. It's authored *before* any run exists.
- A **run**'s artifacts carry an explicit pointer to the narrative version they
  rendered (`narrative_review_id`), instead of being matched by a shared
  `run_id`.

## Data model — canopy-web

### `ReviewRequest` (apps/reviews) → represents a narrative version
Add:
- `feature` (CharField, db_index) — the `narrative_id`. Source of truth for
  which narrative this version belongs to (today derived from `run_id` slug;
  make it explicit and plugin-sent).
- `version` (IntegerField, default 1) — monotonic per `feature`. Assigned
  server-side on create (max(version for feature)+1) unless the client sends one.
- `run_id` becomes optional / advisory for narrative reviews (a narrative
  version is pre-render and not tied to a specific run). Kept for back-compat +
  the `video.walkthrough_id` legacy link.

A "narrative version" = a `ReviewRequest` with a non-empty `narrative` /
`narration`. The **current** version = highest `version` for the feature.

### `Walkthrough` (apps/walkthroughs) → a run's artifact
Add:
- `narrative_review_id` (UUIDField, null, db_index) — the `ReviewRequest`
  (narrative version) this run rendered. Stamped by the plugin at upload.
  (`run_id` and `feature` already exist from the prior change.)

No new top-level `Narrative` or `Run` tables — both stay **read-time
aggregates** (consistent with the current design): a narrative is the set of
walkthroughs + review-versions sharing a `feature`; a run is the walkthroughs
sharing a `run_id`.

## API — `apps/runs` (`/api/ddd`)

- `GET /api/ddd/narratives/` — unchanged shape (list).
- `GET /api/ddd/narratives/{narrative_id}/` — now returns:
  - `current_version` — the latest narrative version (title, story, review_id).
  - `versions[]` — `{version, review_id, title, created_at, gate, status}`
    (newest first) — the **history**.
  - `runs[]` — `{run_id, created_at, status, has_video, has_deck,
    narrative_version}` (which version each run rendered).
- `GET /api/ddd/runs/{run_id}/` — the package, with `narrative` resolved from
  the run's `narrative_review_id` (the version it actually rendered), falling
  back to the narrative's current version when unstamped (legacy).

Aggregation rules (pure functions in `apps/runs/aggregate.py`):
- narrative of a run = explicit `feature` (already source-of-truth).
- a run's narrative version = `narrative_review_id` if set, else the feature's
  current version (legacy fallback).
- versions list = `ReviewRequest`s for the feature, ordered by `version`.

## Plugin contract — canopy (`scripts/ddd`, skills)

1. **Fresh run_id per render.** A DDD loop *render* run is immutable: stop
   resuming + iterating one run_id in place for the purpose of the public
   package. `ddd-run`/`ddd-upload` operate on a run that uploads its converged
   set **once**. Re-rendering → a new `run_id` (the `new_run()` date+NNN scheme
   already supports this; the orchestrator must stop reusing the old id for
   uploads).
2. **Narrative versions are first-class.** `ddd-narrative-review` posts the
   `ReviewRequest` with `feature` (narrative_id) + an incrementing `version`,
   **not** under a run_id. A redraft creates `version+1` (history preserved)
   rather than silently overwriting.
3. **Run → version link.** `ddd-upload` stamps `narrative_review_id` (the
   version the run rendered) on each uploaded artifact. `run_state.yaml` already
   carries `narrative_review_url`; derive the review id from it.
4. **Idempotent / no identical re-publish.** `ddd-upload` uploads exactly one
   hero-video + one docs deck per run. If invoked again for the same run with
   byte-identical content, it is a no-op (skip); if content changed, it should
   be a *new run*, not an append. (Defensive: canopy-web may also de-dup by
   checksum within a run — see Open Questions.)

## Migration of existing data

After deploy, a management command (`apps/runs/management/commands/`):
1. **Backfill `ReviewRequest.feature`** = `feature_from_run_id(run_id)` and
   assign `version` per feature ordered by `created_at`.
2. **Stamp `Walkthrough.narrative_review_id`** = the current (latest-version)
   review for the walkthrough's `feature`, so existing runs link to their
   narrative.
3. **did-monitoring cleanup (the held item):** the `did-monitoring-2026-06-01-001`
   run has 9 artifacts (3 real video renders + 2 byte-identical dupes + 4 decks).
   Migration de-dups by `(role, sha256)` within the run, keeping the newest of
   each identical group. Whether the 3 distinct renders should become 3 separate
   runs is a judgment call deferred to the cleanup step (see Open Questions).

The 4 current narratives (`microplan-to-opp`, `microplans-10-wards`,
`microplans-study-design`, `did-monitoring`) all carry `feature` already, so
they map cleanly; `study-design` becomes a narrative with version history.

## UI — `/ddd` (frontend)

- **Narrative page** (`/ddd/:narrative`): add a **"Story"** panel (current
  version, rendered) with an **edit link** to `/review/<current review_id>` and
  a collapsible **version history** (`v3 · 06-03 · resolved`, each linking to
  its review). Keep the **Runs** list below.
- **Run page** (`/ddd/:narrative/:runId`): the Narrative section shows the
  **specific version this run rendered** (label `narrative v2`) with the edit
  link to that version (reuse the existing `review_id` link, now sourced from
  `narrative_review_id`).

## Open questions (decide before/with build)

1. **Re-render = new run vs same run?** The model says a run is immutable and
   re-rendering mints a new run_id. Confirm the orchestrator should mint a fresh
   run_id for each *render* (not resume), so the narrative shows N runs over
   time. (Recommended: yes.)
2. **Explicit `version` int vs ordered reviews?** Store a real `version` integer
   on `ReviewRequest` (clean labels, stable across re-sorts) vs derive version
   from `created_at` order. (Recommended: explicit int, assigned server-side.)
3. **did-monitoring's 3 distinct video renders** — collapse to one run (keep
   newest) or split into 3 runs? (Recommended: keep newest converged set as the
   one run; it predates the new model.)
4. **Checksum de-dup in canopy-web** — should the upload endpoint reject/replace
   a byte-identical artifact within the same run as a safety net, independent of
   the plugin fix? (Recommended: yes, cheap defense.)

## Out of scope
- No new `Narrative`/`Run` DB tables (stay read-time aggregates).
- No change to walkthrough sharing / tokens.
- Promotion/publishing flow beyond the run package.

## Testing
- `apps/runs`: aggregate unit tests for version history, run→version resolution,
  legacy fallback; API tests for the new narrative-detail shape.
- `apps/reviews`: version assignment on create; feature backfill.
- Migration command tests (version assignment, narrative_review_id stamping,
  checksum de-dup).
- Plugin: `ddd-narrative-review` posts feature+version; `ddd-upload` stamps
  review id + is idempotent on identical content.
- Frontend `npm run build`; dogfood `/ddd` (version history + per-run version).
