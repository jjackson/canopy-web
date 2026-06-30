# ACE read-model parity fixtures

GOLDEN read-model output produced by **ace-web's own `apps/opps` run-reading
code**, captured for a set of representative ACE run folders. This is the
**source of truth** the `apps/agent_runs` (canopy-web) read model is
parity-tested against: rebuild the identical run folders in this project's
`FakeDriveClient`, run the canopy-web read path, project to the same canonical
shape, and assert byte-for-byte equality against the `*.golden.json` here.

## Provenance

- Golden produced from **ace-web `apps/opps`** at commit **`d73e364`**
  (worktree `ace-web/.../beats-x788j`).
- Skill registry (phase / ordinal / has_judge / is_gate per skill) came from
  ace-web's in-repo stub plugin
  `apps/opps/tests/fixtures/stub_plugin/` (frontmatter + `lib/artifact-manifest.ts`)
  — 22 lifecycle skills across 6 phases:
  `design-review → commcare-setup → connect-setup → ocs-setup → llo-management → closeout`.
- Trees were served through ace-web's own `FakeDriveClient`
  (`apps/opps/tests/fixtures/fake_drive.py`).

## Entry points called (what the parity side is matching)

The read model was produced by calling, per run folder:

```python
from apps.opps.sync import load_opp
from apps.opps.tests.fixtures.fake_drive import FakeDriveClient

client = FakeDriveClient.from_tree(tree)          # tree == trees.json → nested dict
ace_id = client.folder_id("ACE")
snap   = load_opp(client, ace_folder_id=ace_id, slug=<slug>)   # -> OppSnapshot
```

`load_opp` dispatches to `apps.opps.sync._load_opp_run` for the multi-run
layout (`ACE/<slug>/runs/<run_id>/`), which internally drives:

- `apps.opps.sync.list_opp_runs` + `_derive_phase_progress` → the **derived
  lifecycle status** (`in_progress` | `complete`) surfaced as `run.status`
  below (via `OppSnapshot.runs_summary[0].lifecycle_status`).
- `apps.opps.skills.SKILL_REGISTRY` + `apps.opps.sync._build_steps` /
  `_extract_step_statuses` → the ordered **steps[]** (status precedence:
  `qa-failed` > run_state declared status > artifact-presence).
- `apps.opps.sync._attribute_files_to_skills` (artifact-manifest driven) →
  **artifacts[]** per skill.
- `apps.opps.sync._load_verdicts` (`JudgeVerdict`) +
  `_load_qa_results` (`QAResult`) → **verdicts[]** (`judge` | `qa`).
- `apps.opps.sync._load_decisions` → **decisions[]**.

`gates[]` are read directly from `run_state.yaml`'s `gates:` map — the same map
ace-web's `POST /opps/<slug>/gates/<skill>` reads/writes. (The read-model
snapshot does not re-surface gates, so the canonical capture sources them from
recorded run state.)

Output dataclasses live in `apps/opps/sync.py` (`OppSnapshot`, `RunDetail`,
`StepSnapshot`, `ArtifactRef`) and `apps/opps/parsers.py` (`StepManifest`,
`JudgeVerdict`, `QAResult`, `Decision`).

## Canonical JSON schema (`*.golden.json`)

A stable, semantic projection of the lifecycle — **NOT** incidental fields
(no Drive file ids, web links, sizes, timestamps, mime types, display names,
previews). Every list is sorted deterministically so equality is order-stable.

```jsonc
{
  "name": "<slug>",
  "run_id": "<run-id>",                     // RunDetail.run_id
  "run": {
    "mode": "review" | "autopilot",         // RunDetail.mode
    "status": "in_progress" | "complete",   // DERIVED (_derive_phase_progress)
    "current_phase": "<phase>" | null,       // RunDetail.current_phase
    "current_step": "<skill>" | null         // RunDetail.current_step
  },
  "steps": [                                // sorted by (ordinal, skill)
    { "skill": "idea-to-pdd", "phase": "design-review",
      "ordinal": 1,
      "status": "pending|running|complete|qa-failed|error|skipped" }
  ],
  "artifacts": [                            // sorted by (skill, name)
    { "skill": "<skill>", "name": "<filename>" }
  ],
  "verdicts": [                             // sorted by (skill, kind)
    { "skill": "<skill>", "kind": "judge",  // JudgeVerdict
      "score": 88.0,                         // 0-100 normalized (null for qa)
      "passed": true },
    { "skill": "<skill>", "kind": "qa",     // QAResult
      "score": null,
      "passed": false }                      // QAResult.verdict == "pass"
  ],
  "decisions": [                            // sorted by (step, question)
    { "step": "<skill>", "question": "...",
      "ai_default": "...", "override": "...",
      "status": "ai-default" | "overridden" }
  ],
  "gates": [                                // sorted by step; from run_state gates:
    { "step": "<skill>", "decision": "pending" | "approved" | "rejected" }
  ]
}
```

### Score normalization note

`verdicts[].score` is whatever `apps.opps.sync._parse_verdict_yaml` produced:
normalized to 0-100 when the verdict YAML declares an explicit `scale:`,
otherwise the raw `overall_score`. These fixtures use 0-100 `overall_score`
with no `scale:` annotation, so scores pass through unchanged.

## The four representative run folders

| golden file | breadth covered |
|---|---|
| `simple_complete.golden.json` | all 22 steps `complete`, derived status `complete`, a couple artifacts, no verdicts/decisions/gates |
| `mid_flight.golden.json` | mix of `complete` / `running` / `pending`; status `in_progress`; cursor on a running step |
| `judge_and_qa_failed.golden.json` | two `judge` verdicts (pass) **and** a `qa`-gated step (`qa-failed` status + failing `QAResult`, eval skipped) |
| `decisions_open_gate.golden.json` | `decisions.yaml` with one `ai-default` + one `overridden` row, plus an **open gate** (`app-deploy: pending`) alongside an `approved` gate |

## `trees.json`

Declarative, FakeDriveClient-agnostic description of each run folder so a
sibling project can rebuild the **identical** tree. Shape:

```jsonc
{
  "ace_root": "ACE",
  "runs": {
    "<key>": {
      "slug": "...", "run_id": "...",
      "opp_files": { "opp.yaml": "<body>" },          // opp-root files (paths relative to ACE/<slug>/)
      "run_files": { "run_state.yaml": "<body>",      // run-folder files (paths relative to ACE/<slug>/runs/<run_id>/)
                     "verdicts/idea-to-pdd-deep.yaml": "<body>", ... }
    }
  }
}
```

Every value is the exact string body to write at that path; folders are implied
by `/` separators. Reconstruct as
`ACE/<slug>/<opp_files paths>` and `ACE/<slug>/runs/<run_id>/<run_files paths>`.

### Layout conventions baked into the trees

- **Multi-run layout**: `ACE/<slug>/opp.yaml` + `ACE/<slug>/runs/<run_id>/...`.
- `run_state.yaml` uses **shape A** — top-level `current_phase`/`current_step`/
  `mode`/`gates` plus a `phases:` map of `{ <phase>: { status, steps: { <skill>: { status } } } }`.
  Step status strings: `done` (→ `complete`), `running`, `pending`.
- **Verdicts**: OLD layout `verdicts/<skill>[-deep|-quick|-monitor].yaml`
  (the shape `artifact-manifest.ts` declares).
- **QA results**: `<N>-<phase>/<producer>-qa_result.yaml` (e.g.
  `2-commcare/pdd-to-deliver-app-qa_result.yaml`).
- **Decisions**: `decisions.yaml` at the run-folder root, canonical top-level
  `decisions:` list.

## Regenerating

Re-run the generator from the ace-web project root (it overwrites the goldens
+ `trees.json`); bump the provenance commit in this README if ace-web's
`apps/opps` read code or stub registry changed.
