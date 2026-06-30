"""ACE read-model parity — the completeness gate for Wave 1 Phase 3.

GOLDEN read-model output (`tests/fixtures/parity/*.golden.json`) was produced by
**ace-web's own `apps/opps` run-reading code** for a set of representative ACE
run folders. This test proves canopy-web's `DriveRunStore` reproduces that read
model for the SAME run folders:

  1. rebuild the IDENTICAL run folder in canopy-web's `FakeDriveClient` from
     `parity/trees.json`,
  2. run `DriveRunStore.get_run` / `list_runs`,
  3. project our read model into the SAME canonical JSON shape the golden uses
     (the `_normalize_run` helper — maps our field names to the golden schema),
  4. assert deep equality with the golden JSON.

When a case diverged, the fix went into the canopy-web *adapter* (store.py /
schemas.py), not into a weakened assertion. The only mappings that live in
`_normalize_run` are documented, intentional shape differences between the two
read models (see the carve-out comments inline).

The skill registry + artifact manifest below are the canopy-side port of
ace-web's in-repo stub plugin (`apps/opps/tests/fixtures/stub_plugin/` —
22 lifecycle skills across 6 phases, the same registry the golden was generated
from). A real deploy injects the live registry into `DriveRunStore`; here we
inject the parity stub so we read the trees exactly as ace-web did.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.agent_runs.drive.store import DriveRunStore, SkillMeta
from apps.agent_runs.schemas import Run
from apps.agent_runs.tests.fixtures.fake_drive import FakeDriveClient

PARITY_DIR = Path(__file__).parent / "fixtures" / "parity"
TREES = json.loads((PARITY_DIR / "trees.json").read_text())


# ---------------------------------------------------------------------------
# The ACE lifecycle stub registry + artifact manifest (the canopy-side port of
# ace-web's stub_plugin the golden was generated from). 22 skills / 6 phases.
# ---------------------------------------------------------------------------
PARITY_SKILL_REGISTRY: list[SkillMeta] = [
    SkillMeta("idea-to-pdd", "design-review", 1),
    SkillMeta("pdd-to-test-prompts", "design-review", 2),
    SkillMeta("pdd-to-learn-app", "commcare-setup", 3),
    SkillMeta("pdd-to-deliver-app", "commcare-setup", 4),
    SkillMeta("app-deploy", "commcare-setup", 5),
    SkillMeta("app-test", "commcare-setup", 6),
    SkillMeta("training-materials", "commcare-setup", 7),
    SkillMeta("connect-program-setup", "connect-setup", 8),
    SkillMeta("connect-opp-setup", "connect-setup", 9),
    SkillMeta("ocs-agent-setup", "ocs-setup", 10),
    SkillMeta("ocs-chatbot-qa", "ocs-setup", 11),
    SkillMeta("ocs-chatbot-eval", "ocs-setup", 12),
    SkillMeta("llo-invite", "llo-management", 13),
    SkillMeta("llo-onboarding", "llo-management", 14),
    SkillMeta("llo-uat", "llo-management", 15),
    SkillMeta("llo-launch", "llo-management", 16),
    SkillMeta("timeline-monitor", "llo-management", 17),
    SkillMeta("flw-data-review", "llo-management", 18),
    SkillMeta("opp-closeout", "closeout", 19),
    SkillMeta("llo-feedback", "closeout", 20),
    SkillMeta("learnings-summary", "closeout", 21),
    SkillMeta("cycle-grade", "closeout", 22),
]

# Path-pinned artifact attribution (the shape ACE's lib/artifact-manifest.ts
# declares). idea.md is an external human input (not a skill output), so it is
# attributed to no step and never surfaces as an artifact — matching the golden.
PARITY_MANIFEST: list[dict] = [
    {"path": "idea.md", "produced_by": "external", "phase": "design-review"},
    {"path": "pdd.md", "produced_by": "idea-to-pdd", "phase": "design-review"},
    {"path": "gate-briefs/idea-to-pdd.md", "produced_by": "idea-to-pdd",
     "phase": "design-review"},
    {"path": "app-summaries/learn-app-summary.md", "produced_by": "pdd-to-learn-app",
     "phase": "commcare-setup"},
    {"path": "app-summaries/deliver-app-summary.md",
     "produced_by": "pdd-to-deliver-app", "phase": "commcare-setup"},
    {"path": "gate-briefs/app-deploy.md", "produced_by": "app-deploy",
     "phase": "commcare-setup"},
    {"path": "connect-setup/program.md", "produced_by": "connect-program-setup",
     "phase": "connect-setup"},
    {"path": "closeout/cycle-grade.md", "produced_by": "cycle-grade",
     "phase": "closeout"},
]


# ---------------------------------------------------------------------------
# Tree rebuild: trees.json → the nested dict FakeDriveClient.from_tree wants.
# ---------------------------------------------------------------------------
def _insert(into: dict, rel_path: str, body: str) -> None:
    """Insert ``body`` at the (``/``-separated) ``rel_path`` into a nested dict,
    creating intermediate folder dicts as needed."""
    parts = rel_path.split("/")
    node = into
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = body


def _build_tree(run_key: str) -> tuple[dict, str, str, str]:
    """Rebuild one ACE run folder from trees.json into the FakeDriveClient nested
    dict. Returns (tree, ace_root, slug, run_id)."""
    ace_root = TREES["ace_root"]
    spec = TREES["runs"][run_key]
    slug = spec["slug"]
    run_id = spec["run_id"]

    opp_dir: dict = {}
    for path, body in spec.get("opp_files", {}).items():
        _insert(opp_dir, path, body)

    run_dir: dict = {}
    for path, body in spec.get("run_files", {}).items():
        _insert(run_dir, path, body)

    opp_dir["runs"] = {run_id: run_dir}
    tree = {ace_root: {slug: opp_dir}}
    return tree, ace_root, slug, run_id


def _store_for(run_key: str) -> tuple[DriveRunStore, str, str]:
    tree, ace_root, slug, run_id = _build_tree(run_key)
    client = FakeDriveClient.from_tree(tree)
    root_id = client.folder_id(f"{ace_root}/{slug}")
    store = DriveRunStore(
        client,
        root_id,
        agent_slug=slug,
        manifest=PARITY_MANIFEST,
        skill_registry=PARITY_SKILL_REGISTRY,
    )
    return store, slug, run_id


# ---------------------------------------------------------------------------
# Read-model → canonical golden JSON projection (the normalization helper).
#
# Every line here is a field-name remap or a DOCUMENTED, intentional shape
# difference between the canopy read model and ACE's. It does NOT recompute or
# relax any lifecycle fact — those come straight from the store.
# ---------------------------------------------------------------------------
def _golden_step_status(step, run: Run) -> str:
    """ACE distinguishes ``qa-failed`` from ``error``; the canopy StepStatus enum
    deliberately collapses both into ``failed`` (it maps onto a DB enum with no
    qa-failed/error). Recover ACE's distinction the same way ACE derives it: a
    step is ``qa-failed`` iff it carries a *failing QA verdict*, else ``error``.
    Non-failed statuses (pending/running/complete/skipped) pass through 1:1."""
    if step.status != "failed":
        return step.status
    has_failing_qa = any(
        v.step_key == step.key and v.kind == "qa" and v.passed is False
        for v in run.verdicts
    )
    return "qa-failed" if has_failing_qa else "error"


def _normalize_run(run: Run) -> dict:
    return {
        # golden.name is the opp slug; the canopy read model surfaces it as
        # `label` (display_name from opp.yaml). These fixtures set
        # display_name == slug (as ACE does for its OppSnapshot.name), so the
        # label IS the slug.
        "name": run.label,
        "run_id": run.id,
        "run": {
            # golden writes the autopilot mode as "autopilot"; the canopy
            # RunMode enum canonicalizes it to "auto". Map back for comparison.
            "mode": "autopilot" if run.mode == "auto" else run.mode,
            "status": run.status,
            "current_phase": run.current_phase or None,
            "current_step": run.current_step or None,
        },
        # steps sorted by (ordinal, skill) — golden ordering.
        "steps": sorted(
            (
                {
                    "skill": s.key,
                    # the canopy Step overloads `title` to carry the phase.
                    "phase": s.title,
                    "ordinal": s.ordinal,
                    "status": _golden_step_status(s, run),
                }
                for s in run.steps
            ),
            key=lambda d: (d["ordinal"], d["skill"]),
        ),
        # artifacts sorted by (skill, name).
        "artifacts": sorted(
            ({"skill": a.step_key, "name": a.name} for a in run.artifacts),
            key=lambda d: (d["skill"], d["name"]),
        ),
        # verdicts sorted by (skill, kind).
        "verdicts": sorted(
            (
                {
                    "skill": v.step_key,
                    "kind": v.kind,
                    "score": v.score,
                    "passed": v.passed,
                }
                for v in run.verdicts
            ),
            key=lambda d: (d["skill"], d["kind"]),
        ),
        # decisions sorted by (step, question).
        "decisions": sorted(
            (
                {
                    "step": d.step_key,
                    "question": d.question,
                    "ai_default": d.ai_default,
                    "override": d.override,
                    "status": d.status,
                }
                for d in run.decisions
            ),
            key=lambda d: (d["step"], d["question"]),
        ),
        # gates sorted by step.
        "gates": sorted(
            ({"step": g.step_key, "decision": g.decision} for g in run.gates),
            key=lambda d: d["step"],
        ),
    }


# ---------------------------------------------------------------------------
# The four representative golden cases.
# ---------------------------------------------------------------------------
GOLDEN_CASES = {
    "simple_complete": "simple_complete.golden.json",
    "mid_flight": "mid_flight.golden.json",
    "judge_and_qa_failed": "judge_and_qa_failed.golden.json",
    "decisions_open_gate": "decisions_open_gate.golden.json",
}


@pytest.mark.parametrize("run_key", sorted(GOLDEN_CASES))
def test_drive_run_matches_ace_golden(run_key: str):
    """DriveRunStore.get_run reproduces ace-web's read model byte-for-byte
    (after canonical projection) for the same run folder."""
    golden = json.loads((PARITY_DIR / GOLDEN_CASES[run_key]).read_text())

    store, slug, run_id = _store_for(run_key)
    run = store.get_run(slug, run_id)
    actual = _normalize_run(run)

    assert actual == golden, (
        f"parity divergence for {run_key}:\n"
        f"actual={json.dumps(actual, indent=2, sort_keys=True)}"
    )


@pytest.mark.parametrize("run_key", sorted(GOLDEN_CASES))
def test_list_runs_header_matches_golden(run_key: str):
    """list_runs surfaces the same run header (status / mode / phase / step) as
    the golden — the cheap-status path (run_state-only, no tree walk) must agree
    with the deep get_run path."""
    golden = json.loads((PARITY_DIR / GOLDEN_CASES[run_key]).read_text())

    store, slug, run_id = _store_for(run_key)
    summaries = store.list_runs(slug)

    assert [s.id for s in summaries] == [run_id]
    s = summaries[0]
    assert s.status == golden["run"]["status"]
    assert ("autopilot" if s.mode == "auto" else s.mode) == golden["run"]["mode"]
    assert (s.current_phase or None) == golden["run"]["current_phase"]
    assert (s.current_step or None) == golden["run"]["current_step"]
    assert s.label == golden["name"]


# ---------------------------------------------------------------------------
# Fork parity (no golden fork case exists, so this is a canopy-side check
# derived from a golden tree). Forking a review-mode golden run at a clean phase
# boundary must yield: kept steps complete, fork-onward pending, run in_progress,
# forked_from pinned to the source — the FORK_MODES contract the DB / in-memory
# adapters also satisfy.
# ---------------------------------------------------------------------------
def test_fork_parity_from_golden_tree():
    store, slug, run_id = _store_for("mid_flight")

    # Fork at ordinal-3 (pdd-to-learn-app): the whole design-review phase
    # (ordinals 1-2) is kept; commcare-setup onward is re-run.
    summary = store.fork(slug, run_id, at_step="pdd-to-learn-app")

    assert summary.forked_from == run_id
    assert summary.status == "in_progress"
    assert summary.id != run_id

    forked = store.get_run(slug, summary.id)
    assert forked.forked_from == run_id
    # mid_flight is review-mode, so the fork stays review (no autopilot rabbit
    # hole — see the mode carve-out in _normalize_run).
    assert forked.mode == "review"

    by_skill = {s.key: s for s in forked.steps}
    kept = {"idea-to-pdd", "pdd-to-test-prompts"}
    for s in forked.steps:
        if s.key in kept:
            assert s.status == "complete", f"{s.key} should be kept→complete"
        else:
            assert s.status == "pending", f"{s.key} should be fork-onward→pending"

    # The fork point itself is the first re-run step.
    assert by_skill["pdd-to-learn-app"].status == "pending"
    assert forked.current_step == "pdd-to-learn-app"
