"""DriveRunStore parity: an ACE-shaped Drive run-folder → the read model.

Builds a representative run folder in the FakeDriveClient (run_state.yaml with
a phases map + gates, a verdicts/ file, a decisions.yaml, and a couple of
``<N>-<phase>/`` artifact files), then asserts DriveRunStore returns a
complete, correct read model interchangeable with the DB adapter:

  * steps in registry order, statuses derived from run_state.yaml
  * artifacts attributed to the producing skill
  * judge + QA verdicts attached to the right step
  * the decisions log + gates parsed through
  * run status derived from the steps map

Plus the writes (record_gate / record_decision), changed_ids via the Changes
API, and the deferred fork.
"""
import datetime as dt

import pytest

from canopy_agent_runs.drive.store import DriveRunStore, SkillMeta
from canopy_agent_runs.schemas import Run, RunSummary
from canopy_agent_runs.stores import RunStore
from tests.fixtures.fake_drive import FakeDriveClient

AGENT = "goofy-geese"
RUN_ID = "20260620-1200"

# Manifest: declare the one path-pinned artifact; the learn-app summary is
# recovered by the <N>-<phase>/<skill>_<role> filename-prefix fallback.
MANIFEST = [
    {"path": "idea.md", "produced_by": "external", "phase": "1-design"},
    {"path": "1-design/pdd.md", "produced_by": "idea-to-pdd", "phase": "1-design"},
]

REGISTRY = [
    SkillMeta("idea-to-pdd", "1-design", 1),
    SkillMeta("pdd-to-learn-app", "2-build", 2),
    SkillMeta("pdd-to-deliver-app", "2-build", 3),
    SkillMeta("app-test", "2-build", 4),
]

_RUN_STATE = """\
mode: review
started_at: 2026-06-20T12:00:00Z
current_step: app-test
display_name: Goofy Geese Demo (run_state fallback)
phases:
  1-design:
    status: complete
    steps:
      idea-to-pdd: {status: done}
  2-build:
    status: running
    steps:
      pdd-to-learn-app: {status: done}
      pdd-to-deliver-app: {status: skipped}
      app-test: {status: running}
gates:
  idea-to-pdd:
    decision: approved
    decided_by: ace@dimagi-ai.com
    decided_at: 2026-06-20T12:05:00Z
    note: ''
"""

_DECISIONS = """\
schema_version: 3
decisions:
  - id: archetype-selection
    phase: 1-design
    skill: idea-to-pdd
    question: Which archetype?
    ai-default: atomic-visit
    options: [atomic-visit, focus-group]
    source: idea-pack
    status: ai-default
"""

_JUDGE = """\
skill: idea-to-pdd
verdict: pass
overall_score: 87
evaluated_at: 2026-06-20T12:04:00Z
summary: solid PDD
"""

_QA = """\
verdict: pass
ran_at: 2026-06-20T12:03:00Z
stats: {checks_run: 4, checks_passed: 4, checks_failed: 0}
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
                        "verdicts": {
                            "idea-to-pdd-deep.yaml": _JUDGE,
                        },
                        "1-design": {
                            "pdd.md": "# Goofy Geese PDD",
                            "idea-to-pdd-qa_result.yaml": _QA,
                        },
                        "2-build": {
                            "pdd-to-learn-app_summary.md": "# Learn app summary\nnova_app_id: abc",
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


# --- Protocol conformance ---


def test_drive_store_satisfies_runstore_protocol():
    assert isinstance(_store(), RunStore)


def test_record_verdict_is_read_through_only():
    """ACE writes its own verdicts/*.yaml; the Drive adapter does not write them.
    Canopy-hosted agents record verdicts via the DB store instead."""
    with pytest.raises(NotImplementedError, match="read-through"):
        _store().record_verdict(AGENT, "any-run", "render", kind="judge", score=80.0)


# --- get_run: the full read model ---


def test_get_run_returns_complete_read_model():
    run = _store().get_run(AGENT, RUN_ID)
    assert isinstance(run, Run)
    assert run.id == RUN_ID
    assert run.agent_slug == AGENT
    assert run.label == "Goofy Geese Demo"  # opp.yaml wins over run_state
    assert run.mode == "review"
    assert run.current_step == "app-test"
    assert run.created_at == dt.datetime(2026, 6, 20, 12, 0, tzinfo=dt.timezone.utc)


def test_steps_in_registry_order_with_derived_statuses():
    run = _store().get_run(AGENT, RUN_ID)
    assert [s.key for s in run.steps] == [
        "idea-to-pdd",
        "pdd-to-learn-app",
        "pdd-to-deliver-app",
        "app-test",
    ]
    assert [s.ordinal for s in run.steps] == [1, 2, 3, 4]
    assert [s.status for s in run.steps] == [
        "complete",
        "complete",
        "skipped",
        "running",
    ]


def test_run_status_derived_from_steps():
    # app-test still running → the whole run is in_progress.
    run = _store().get_run(AGENT, RUN_ID)
    assert run.status == "in_progress"


def test_artifacts_attributed_to_producing_skill():
    run = _store().get_run(AGENT, RUN_ID)
    by_step: dict[str, list[str]] = {}
    for a in run.artifacts:
        by_step.setdefault(a.step_key, []).append(a.name)
    assert "pdd.md" in by_step["idea-to-pdd"]  # manifest path match
    assert "pdd-to-learn-app_summary.md" in by_step["pdd-to-learn-app"]  # prefix fallback
    # The QA-result yaml is consumed by the QA loader, not surfaced as an artifact.
    assert "idea-to-pdd-qa_result.yaml" not in [a.name for a in run.artifacts]


def test_artifact_ref_and_path_populated_from_drive_data():
    # The Drive adapter surfaces the Drive file id (opaque stable handle) as
    # Artifact.ref and the run-relative path as Artifact.path — both from data
    # it already holds during attribution. ace-web reads these instead of
    # re-deriving them.
    run = _store().get_run(AGENT, RUN_ID)
    pdd = next(a for a in run.artifacts if a.name == "pdd.md")
    assert pdd.path == "1-design/pdd.md"
    assert pdd.ref  # non-empty Drive file id
    assert pdd.url.endswith(pdd.ref)  # url is https://fake/<ref> for this client
    summary = next(
        a for a in run.artifacts if a.name == "pdd-to-learn-app_summary.md"
    )
    assert summary.path == "2-build/pdd-to-learn-app_summary.md"
    assert summary.ref


def test_judge_and_qa_verdicts_attached_to_step():
    run = _store().get_run(AGENT, RUN_ID)
    judges = [v for v in run.verdicts if v.kind == "judge"]
    qas = [v for v in run.verdicts if v.kind == "qa"]
    assert len(judges) == 1
    assert judges[0].step_key == "idea-to-pdd"
    assert judges[0].score == 87.0
    assert judges[0].passed is True
    assert judges[0].evaluated_at == dt.datetime(
        2026, 6, 20, 12, 4, tzinfo=dt.timezone.utc
    )
    assert len(qas) == 1
    assert qas[0].step_key == "idea-to-pdd"
    assert qas[0].passed is True
    assert qas[0].criteria["checks_run"] == 4


def test_decisions_log_parsed_through():
    run = _store().get_run(AGENT, RUN_ID)
    assert len(run.decisions) == 1
    d = run.decisions[0]
    assert d.step_key == "idea-to-pdd"
    assert d.question == "Which archetype?"
    assert d.ai_default == "atomic-visit"
    assert d.status == "ai-default"
    # Generic decisions-log fields the Drive adapter already parses are now
    # threaded through to the read model (previously dropped).
    assert d.id == "archetype-selection"
    assert d.phase == "1-design"
    assert d.options_considered == ["atomic-visit", "focus-group"]
    assert d.source == "idea-pack"
    assert d.override_reasoning == ""
    assert d.conflict_signals == []


def test_gates_parsed_from_run_state():
    run = _store().get_run(AGENT, RUN_ID)
    assert len(run.gates) == 1
    g = run.gates[0]
    assert g.step_key == "idea-to-pdd"
    assert g.decision == "approved"
    assert g.decided_by == "ace@dimagi-ai.com"
    assert g.is_open is False
    assert g.decided_at == dt.datetime(2026, 6, 20, 12, 5, tzinfo=dt.timezone.utc)


# --- list views ---


def test_list_runs_returns_summary_with_derived_status():
    summaries = _store().list_runs(AGENT)
    assert len(summaries) == 1
    s = summaries[0]
    assert isinstance(s, RunSummary)
    assert s.id == RUN_ID
    assert s.agent_slug == AGENT
    assert s.status == "in_progress"
    assert s.label == "Goofy Geese Demo"


def test_list_artifacts_filters_by_step_key():
    store = _store()
    only = store.list_artifacts(AGENT, RUN_ID, step_key="pdd-to-learn-app")
    assert {a.name for a in only} == {"pdd-to-learn-app_summary.md"}


# --- writes ---


def test_record_gate_writes_run_state_and_is_readable_back():
    store = _store()
    gate = store.record_gate(
        AGENT, RUN_ID, "app-test", "approved", decided_by="neal@dimagi.com",
        note="ship it",
    )
    assert gate.step_key == "app-test"
    assert gate.is_open is False

    # Re-read from Drive: the new gate is now persisted in run_state.yaml,
    # alongside the pre-existing idea-to-pdd gate.
    run = store.get_run(AGENT, RUN_ID)
    gates = {g.step_key: g for g in run.gates}
    assert set(gates) == {"idea-to-pdd", "app-test"}
    assert gates["app-test"].decision == "approved"
    assert gates["app-test"].decided_by == "neal@dimagi.com"
    assert gates["app-test"].note == "ship it"


def test_record_decision_appends_to_log():
    store = _store()
    store.record_decision(
        AGENT, RUN_ID, "app-test",
        {"question": "Manual or automated tests?", "ai_default": "automated"},
    )
    run = store.get_run(AGENT, RUN_ID)
    questions = {(d.step_key, d.question) for d in run.decisions}
    assert ("app-test", "Manual or automated tests?") in questions
    assert ("idea-to-pdd", "Which archetype?") in questions


# --- cache invalidation ---


def test_changed_ids_via_changes_api():
    store = _store()
    changed, cursor = store.changed_ids(AGENT)  # seed
    assert changed == []
    assert cursor

    store.record_gate(AGENT, RUN_ID, "app-test", "approved")
    changed, _ = store.changed_ids(AGENT, cursor)
    assert RUN_ID in changed


# --- fork (smoke; full coverage in test_drive_fork.py) ---


def test_fork_mints_a_new_run_under_the_same_agent():
    store = _store()
    summary = store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="keep-all")
    assert isinstance(summary, RunSummary)
    assert summary.id != RUN_ID
    assert summary.agent_slug == AGENT
    assert summary.forked_from == RUN_ID
    assert summary.current_step == "pdd-to-learn-app"
    # the new run is now listable alongside the source
    assert {s.id for s in store.list_runs(AGENT)} == {RUN_ID, summary.id}


def test_fork_rejects_unknown_mode_and_step():
    store = _store()
    with pytest.raises(ValueError):
        store.fork(AGENT, RUN_ID, "pdd-to-learn-app", mode="bogus")
    with pytest.raises(ValueError):
        store.fork(AGENT, RUN_ID, "nope")
