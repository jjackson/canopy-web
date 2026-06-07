# DDD Narrative / Run / Version model — design spec

**Date:** 2026-06-03
**Status:** Shipped (annotated 2026-06-07) — PRs #80, #82, #95. The narrative → version → run model described here is the current implementation (`apps/runs/`, `narrative_slug`).
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

## Target model (strict hierarchy)

A run belongs to exactly one narrative version. Versions group the story's
history; **runs nest under the version they rendered**.

```
Narrative  (stable narrative_id, e.g. "did-monitoring")     ← the thing you're demoing
├─ Narrative version v1   (story draft 1; an editable ReviewRequest)
│    ├─ run did-monitoring-2026-06-01-001   → video + deck + links   (immutable)
│    └─ run did-monitoring-2026-06-01-002   → …
└─ Narrative version v2   (story re-drafted)
     ├─ run did-monitoring-2026-06-03-001   → …
     └─ run did-monitoring-2026-06-03-002   → …
```

- **Narrative versions** — the story, iterated over time (re-draft, scene
  edits). Each is a `ReviewRequest` (the editable surface), keyed by
  `(narrative_id, version)`. The highest version is "current."
- **Runs** — each DDD loop render mints a **fresh** `run_id` and produces one
  **immutable** artifact set. A run is **attached to a specific narrative
  version** (the version it rendered) and is listed under it. Re-rendering is a
  *new run* under the same (or a newer) version — never an in-place append.

`/ddd` navigation:
- **L1 Narratives** — list (title, run count, latest activity, current phase).
- **L2 Narrative** — the **version history**; each version shows its story (+
  edit link to the review) and, nested beneath it, **its runs** (newest first).
- **L3 Run** — the frozen package (video + deck + links) + a breadcrumb to its
  narrative version (+ edit link to that version).

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
- `GET /api/ddd/narratives/{narrative_id}/` — returns the **version-grouped**
  tree:
  - `current_version` — the latest narrative version (title, story, review_id).
  - `versions[]` (newest first), each:
    `{version, review_id, title, created_at, gate, status, runs[]}` where
    `runs[]` = `{run_id, created_at, status, has_video, has_deck}` for the runs
    attached to that version (newest first).
  - Legacy runs whose `narrative_review_id` is unset attach to the current
    version (or an `unversioned` bucket — see Open Questions).
- `GET /api/ddd/runs/{run_id}/` — the package, with `narrative` resolved from
  the run's `narrative_review_id` (the version it actually rendered), plus
  `narrative_version` (the int) for the breadcrumb. Falls back to the
  narrative's current version when unstamped (legacy).

Aggregation rules (pure functions in `apps/runs/aggregate.py`):
- narrative of a run = explicit `feature` (already source-of-truth).
- a run's version = the `version` of its `narrative_review_id` review; if unset,
  the feature's current version.
- versions list = `ReviewRequest`s for the feature, ordered by `version`; each
  version's `runs[]` = walkthroughs grouped by `run_id` whose
  `narrative_review_id` resolves to that version.

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
   be a *new run*, not an append. canopy-web stays append-only (no server-side
   checksum guard — Decision 5); idempotency is the plugin's responsibility.

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

- **Narrative page** (`/ddd/:narrative`): a **version-grouped** list. The
  current version is expanded by default — its story (rendered) + **edit link**
  to `/review/<review_id>` + its **runs** nested beneath. Older versions
  collapse under a `▸ v2 · 06-03` disclosure, each expanding to its own story +
  runs. (Left nav mirrors this: narrative → version → run.)
- **Run page** (`/ddd/:narrative/:runId`): the package + a **breadcrumb**
  `narrative › v2 › run`, and the Narrative section shows the **specific version
  this run rendered** (label `narrative v2`) with the edit link to that version
  (the existing `review_id` link, now sourced from `narrative_review_id`).

## Decisions (locked)

1. **Runs nest under versions.** A run is attached to exactly one narrative
   version (`narrative_review_id`) and is listed beneath it. Narrative →
   version → run is a strict hierarchy.
2. **Fresh run_id per render.** A render is an immutable run; the orchestrator
   mints a new run_id each render and never resumes-in-place for the package.
3. **Explicit `version` int** on `ReviewRequest`, assigned server-side
   (monotonic per `feature`).
4. **did-monitoring cleanup:** keep the newest converged video+deck as the one
   run; de-dup the byte-identical extras. (Held until this lands; done as part
   of the migration.)
5. **No server-side checksum guard** — rely on the plugin's idempotent upload to
   prevent duplicate re-publishes. (Revisit if a buggy client reappears.)

## Open questions (decide during build)

- **Legacy unversioned runs** — runs with no `narrative_review_id` after
  backfill: attach to the feature's current version, or show in a separate
  `unversioned` bucket on the narrative page? (Lean: attach to current version,
  since the backfill stamps them anyway.)

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
