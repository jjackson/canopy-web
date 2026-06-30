"""DriveRunStore.fork parity — ported from ace-web apps/opps/opp_forker.py.

Builds a 3-phase ACE-shaped run in the FakeDriveClient, forks it at the MIDDLE
phase in both modes, and asserts (via get_run) that the new run's read model is
interchangeable with what the DB/in-memory adapters' fork produces:

  * kept (pre-fork) steps land 'complete', the fork step onward 'pending';
  * run status derives to 'in_progress';
  * only kept-step decisions carry forward, mode-filtered (+ edits);
  * the kept phase folder's artifacts/verdict carry; trimmed phases don't;
  * idea.md / inputs-manifest.yaml carry verbatim; the source run is untouched.

The fork point is a phase BOUNDARY (the first step of the middle phase) so the
Drive store's phase-granular folder copy and step-granular statuses agree —
see the module docstring's interior-fork caveat.
"""
import datetime as dt

import pytest
import yaml

from canopy_runs.drive.store import DriveRunStore, SkillMeta
from canopy_runs.schemas import RunSummary
from tests.fixtures.fake_drive import FakeDriveClient

AGENT = "goofy-geese"
RUN_ID = "20260101-1000"

MANIFEST = [
    {"path": "idea.md", "produced_by": "external", "phase": "1-design"},
    {"path": "1-design/pdd.md", "produced_by": "idea-to-pdd", "phase": "1-design"},
]

# Three phases, one step each → the fork at the middle phase ('pdd-to-learn-app')
# keeps phase 1 only.
REGISTRY = [
    SkillMeta("idea-to-pdd", "1-design", 1),
    SkillMeta("pdd-to-learn-app", "2-build", 2),
    SkillMeta("pdd-to-deliver-app", "3-deliver", 3),
]

# Source run: fully complete, all three phases done.
_RUN_STATE = """\
mode: review
started_at: 2026-01-01T10:00:00Z
current_step: pdd-to-deliver-app
phases:
  1-design:
    status: complete
    steps:
      idea-to-pdd: {status: done}
  2-build:
    status: complete
    steps:
      pdd-to-learn-app: {status: done}
  3-deliver:
    status: complete
    steps:
      pdd-to-deliver-app: {status: done}
"""

# Decisions across all three phases. d-archetype (ai-default) + d-tone
# (overridden) are in the kept phase; d-framework + d-channel are downstream.
# Note d-channel is OVERRIDDEN but downstream — the canopy contract drops it
# (only kept-step rows survive), unlike ace-web's "overridden survives any
# phase" carveout. That divergence is asserted below.
_DECISIONS = """\
schema_version: 3
decisions:
  - id: archetype-selection
    phase: 1-design
    skill: idea-to-pdd
    question: Which archetype?
    ai-default: atomic-visit
    options: [atomic-visit, focus-group]
    status: ai-default
  - id: tone-selection
    phase: 1-design
    skill: idea-to-pdd
    question: Tone?
    ai-default: formal
    override: casual
    options: [formal, casual]
    status: overridden
  - id: framework-selection
    phase: 2-build
    skill: pdd-to-learn-app
    question: Framework?
    ai-default: react
    options: [react, vue]
    status: ai-default
  - id: channel-selection
    phase: 3-deliver
    skill: pdd-to-deliver-app
    question: Channel?
    ai-default: sms
    override: whatsapp
    options: [sms, whatsapp]
    status: overridden
"""

_JUDGE = """\
skill: idea-to-pdd
verdict: pass
overall_score: 87
evaluated_at: 2026-01-01T10:04:00Z
summary: solid PDD
"""


def _tree() -> dict:
    return {
        "agents": {
            AGENT: {
                "opp.yaml": "display_name: Goofy Geese Demo\nslug: goofy-geese\n",
                "runs": {
                    RUN_ID: {
                        "run_state.yaml": _RUN_STATE,
                        "decisions.yaml": _DECISIONS,
                        "idea.md": "Seed idea for the goofy geese.",
                        "inputs-manifest.yaml": "manifest: true\n",
                        "1-design": {
                            "pdd.md": "# Goofy Geese PDD",
                            "idea-to-pdd_verdict.yaml": _JUDGE,
                        },
                        "2-build": {
                            "pdd-to-learn-app_summary.md": "# Learn app summary",
                        },
                        "3-deliver": {
                            "pdd-to-deliver-app_summary.md": "# Deliver app summary",
                        },
                    },
                },
            }
        }
    }


def _store() -> DriveRunStore:
    client = FakeDriveClient.from_tree(_tree())
    root = client.folder_id(f"agents/{AGENT}")
    return DriveRunStore(
        client, root, agent_slug=AGENT, manifest=MANIFEST, skill_registry=REGISTRY
    )


# --- the summary the fork returns ---


def test_fork_returns_summary_for_new_run():
    store = _store()
    summary = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-all")
    assert isinstance(summary, RunSummary)
    assert summary.id != RUN_ID
    assert summary.agent_slug == AGENT
    assert summary.label == "Goofy Geese Demo"  # carried from opp.yaml
    assert summary.mode == "review"
    assert summary.current_step == "pdd-to-learn-app"
    assert summary.forked_from == RUN_ID
    assert summary.status == "in_progress"  # phase-1 done, 2 & 3 pending


# --- steps: kept→complete, fork-onward→pending ---


def test_forked_steps_done_and_pending(monkeypatch):
    store = _store()
    summary = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-all")
    forked = store.get_run(AGENT, summary.id)
    assert {s.key: s.status for s in forked.steps} == {
        "idea-to-pdd": "complete",
        "pdd-to-learn-app": "pending",
        "pdd-to-deliver-app": "pending",
    }
    assert [s.ordinal for s in forked.steps] == [1, 2, 3]
    assert forked.status == "in_progress"


# --- decisions: kept-step only, mode-filtered, edited ---


def test_fork_keep_all_carries_kept_step_decisions():
    store = _store()
    summary = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-all")
    forked = store.get_run(AGENT, summary.id)
    carried = {(d.step_key, d.question) for d in forked.decisions}
    # Both phase-1 (idea-to-pdd) rows carry; the downstream rows drop — even the
    # OVERRIDDEN channel-selection (pdd-to-deliver-app is not a kept step).
    assert carried == {
        ("idea-to-pdd", "Which archetype?"),
        ("idea-to-pdd", "Tone?"),
    }


def test_fork_keep_overrides_only_drops_kept_ai_defaults():
    store = _store()
    summary = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-overrides-only")
    forked = store.get_run(AGENT, summary.id)
    carried = [(d.step_key, d.question, d.status) for d in forked.decisions]
    # Only the overridden phase-1 row survives; the ai-default archetype drops.
    assert carried == [("idea-to-pdd", "Tone?", "overridden")]


def test_fork_applies_edits_to_kept_decision():
    store = _store()
    edits = {
        "idea-to-pdd": {
            "Which archetype?": {"override": "focus-group", "reasoning": "wider net"}
        }
    }
    summary = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-all", edits=edits)
    forked = store.get_run(AGENT, summary.id)
    archetype = next(d for d in forked.decisions if d.question == "Which archetype?")
    assert archetype.override == "focus-group"
    assert archetype.status == "overridden"
    assert archetype.reasoning == "wider net"
    assert archetype.ai_default == "atomic-visit"  # the AI default is preserved


def test_fork_edit_string_shorthand_sets_override():
    store = _store()
    # A bare-string edit is the override answer (mirrors _apply_decision_edit).
    edits = {"idea-to-pdd": {"Which archetype?": "focus-group"}}
    summary = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-all", edits=edits)
    forked = store.get_run(AGENT, summary.id)
    archetype = next(d for d in forked.decisions if d.question == "Which archetype?")
    assert archetype.override == "focus-group"
    assert archetype.status == "overridden"


# --- artifacts + verdict: kept phase carries, trimmed phases don't ---


def test_fork_carries_kept_phase_artifacts_only():
    store = _store()
    summary = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-all")
    forked = store.get_run(AGENT, summary.id)
    by_step: dict[str, list[str]] = {}
    for a in forked.artifacts:
        by_step.setdefault(a.step_key, []).append(a.name)
    # phase-1 (idea-to-pdd) artifact carried via the copied 1-design/ folder.
    assert "pdd.md" in by_step.get("idea-to-pdd", [])
    # The trimmed phases' artifacts did NOT carry.
    assert "pdd-to-learn-app" not in by_step
    assert "pdd-to-deliver-app" not in by_step


def test_fork_carries_kept_phase_verdict():
    store = _store()
    summary = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-all")
    forked = store.get_run(AGENT, summary.id)
    judges = [v for v in forked.verdicts if v.kind == "judge"]
    assert [j.step_key for j in judges] == ["idea-to-pdd"]
    assert judges[0].score == 87.0
    assert judges[0].passed is True


# --- Drive-side effects: new folder layout + source untouched ---


def test_fork_writes_expected_drive_layout():
    store = _store()
    client = store.client
    summary = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-all")

    new_run_path = f"agents/{AGENT}/runs/{summary.id}"
    children = {c.name for c in client.list_folder(client.folder_id(new_run_path))}
    # Synthesized + carried run-root files.
    assert "run_state.yaml" in children
    assert "decisions.yaml" in children
    assert "idea.md" in children
    assert "inputs-manifest.yaml" in children
    # Kept phase folder copied; trimmed phase folders are NOT.
    assert "1-design" in children
    assert "2-build" not in children
    assert "3-deliver" not in children

    # The kept phase subtree carried verbatim.
    design = {
        c.name
        for c in client.list_folder(client.folder_id(f"{new_run_path}/1-design"))
    }
    assert "pdd.md" in design

    # Synthesized run_state marks the kept phase done/seeded, fork-onward pending.
    state = yaml.safe_load(
        client.get_content(
            client.file_id(f"{new_run_path}/run_state.yaml"), "application/x-yaml"
        ).content
    )
    assert state["forked_from"] == RUN_ID
    assert state["current_step"] == "pdd-to-learn-app"
    assert state["phases"]["1-design"]["status"] == "done"
    assert state["phases"]["1-design"]["verdict"] == "seeded"
    assert state["phases"]["1-design"]["completed_at"]
    assert state["phases"]["2-build"]["status"] == "pending"
    assert state["phases"]["3-deliver"]["status"] == "pending"


def test_fork_leaves_source_run_untouched():
    store = _store()
    store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-overrides-only")
    src = store.get_run(AGENT, RUN_ID)
    # All four source decisions still present; statuses unchanged.
    assert {(d.step_key, d.question) for d in src.decisions} == {
        ("idea-to-pdd", "Which archetype?"),
        ("idea-to-pdd", "Tone?"),
        ("pdd-to-learn-app", "Framework?"),
        ("pdd-to-deliver-app", "Channel?"),
    }
    # Source steps all complete; status unchanged.
    assert {s.status for s in src.steps} == {"complete"}


# --- validation ---


def test_fork_rejects_unknown_mode():
    with pytest.raises(ValueError):
        _store().fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="bogus")


def test_fork_rejects_unknown_step():
    with pytest.raises(ValueError):
        _store().fork(AGENT, RUN_ID, "no-such-step")


# --- two forks in the same minute get distinct sortable ids ---


def test_two_forks_get_distinct_run_ids():
    store = _store()
    a = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-all")
    b = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-all")
    assert a.id != b.id
    ids = {s.id for s in store.list_runs(AGENT)}
    assert {RUN_ID, a.id, b.id} <= ids
