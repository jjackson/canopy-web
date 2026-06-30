"""InMemoryRunStore behaviour — the reference adapter."""
from __future__ import annotations

import datetime as dt

import pytest

from canopy_runs.schemas import (
    Artifact,
    Decision,
    Gate,
    Run,
    Step,
    Verdict,
)
from canopy_runs.stores import InMemoryRunStore, RunStore


def _sample_run(run_id: str = "r1", agent: str = "echo", created: dt.datetime | None = None) -> Run:
    created = created or dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    return Run(
        id=run_id,
        agent_slug=agent,
        label="demo run",
        mode="review",
        current_step="render",
        session_link="https://example.com/session",
        created_at=created,
        steps=[
            Step(key="spec", ordinal=0, title="Spec", status="complete"),
            Step(key="render", ordinal=1, title="Render", status="running"),
        ],
        artifacts=[Artifact(step_key="render", name="hero.mp4", url="gs://x", role="walkthrough")],
        verdicts=[Verdict(step_key="render", kind="qa", passed=True)],
        decisions=[Decision(step_key="spec", question="which persona?", ai_default="flw", status="ai-default")],
        gates=[Gate(step_key="render")],
    )


def test_inmemory_satisfies_protocol():
    assert isinstance(InMemoryRunStore(), RunStore)


def test_get_run_derives_status():
    store = InMemoryRunStore()
    store.put_run(_sample_run())
    run = store.get_run("echo", "r1")
    assert run.status == "in_progress"  # render still running
    assert run.label == "demo run"
    assert run.session_link == "https://example.com/session"


def test_list_runs_sorted_newest_first():
    store = InMemoryRunStore()
    store.put_run(_sample_run("r1", created=dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)))
    store.put_run(_sample_run("r2", created=dt.datetime(2026, 6, 5, tzinfo=dt.timezone.utc)))
    ids = [s.id for s in store.list_runs("echo")]
    assert ids == ["r2", "r1"]


def test_list_artifacts_filtered_by_step():
    store = InMemoryRunStore()
    store.put_run(_sample_run())
    assert len(store.list_artifacts("echo", "r1")) == 1
    assert store.list_artifacts("echo", "r1", step_key="spec") == []
    assert len(store.list_artifacts("echo", "r1", step_key="render")) == 1


def test_list_steps_and_verdicts():
    store = InMemoryRunStore()
    store.put_run(_sample_run())
    assert [s.key for s in store.list_steps("echo", "r1")] == ["spec", "render"]
    verdicts = store.list_verdicts("echo", "r1")
    assert len(verdicts) == 1 and verdicts[0].kind == "qa"


def test_record_gate_closes_open_gate():
    store = InMemoryRunStore()
    store.put_run(_sample_run())
    gate = store.record_gate("echo", "r1", "render", decision="approve", decided_by="jj@x.com")
    assert gate.is_open is False
    assert gate.decision == "approve"
    # re-read: the gate on the run is now decided
    run = store.get_run("echo", "r1")
    assert run.gates[0].decided_at is not None


def test_changed_ids_tracks_writes():
    store = InMemoryRunStore()
    store.put_run(_sample_run("r1"))
    ids, cursor = store.changed_ids("echo")
    assert "r1" in ids
    # nothing new since cursor
    ids2, _ = store.changed_ids("echo", cursor)
    assert ids2 == []
    store.record_gate("echo", "r1", "render", decision="approve")
    ids3, _ = store.changed_ids("echo", cursor)
    assert ids3 == ["r1"]


def test_record_verdict_appends_and_aggregates():
    store = InMemoryRunStore()
    store.put_run(_sample_run())
    v = store.record_verdict("echo", "r1", "render", kind="judge", score=82.0, rationale="solid")
    assert isinstance(v, Verdict)
    assert (v.kind, v.score, v.step_key) == ("judge", 82.0, "render")
    assert v.evaluated_at is not None
    run = store.get_run("echo", "r1")
    assert run.verdicts[-1].score == 82.0
    assert run.overall_score == 82.0          # weakest-link over the single judge verdict
    assert run.qa_gate_ok is True             # the sample's qa verdict passed


def test_record_verdict_tracked_as_write():
    store = InMemoryRunStore()
    store.put_run(_sample_run("r1"))
    _, cursor = store.changed_ids("echo")
    store.record_verdict("echo", "r1", "render", kind="qa", passed=False)
    ids, _ = store.changed_ids("echo", cursor)
    assert ids == ["r1"]


def test_missing_run_raises():
    store = InMemoryRunStore()
    with pytest.raises(KeyError):
        store.get_run("echo", "nope")


def test_new_artifact_and_decision_fields_default_safely():
    # Storage-agnostic adapters (in-memory, DB) that don't carry the enriched
    # Drive provenance construct the read model fine — the new fields take their
    # safe defaults (empty string / empty list), never required.
    store = InMemoryRunStore()
    store.put_run(_sample_run())
    run = store.get_run("echo", "r1")

    art = run.artifacts[0]
    assert art.ref == ""
    assert art.path == ""

    dec = run.decisions[0]
    assert dec.id == ""
    assert dec.phase == ""
    assert dec.options_considered == []
    assert dec.source == ""
    assert dec.override_reasoning == ""
    assert dec.conflict_signals == []
