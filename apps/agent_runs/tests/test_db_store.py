"""DbRunStore read path — create ORM rows, assert the read model matches."""
from __future__ import annotations

import datetime as dt

import pytest

from apps.agent_runs.models import (
    AgentRun,
    AgentRunArtifact,
    AgentRunDecision,
    AgentRunGate,
    AgentRunStep,
    AgentRunVerdict,
)
from apps.agent_runs.stores import DbRunStore, RunStore
from apps.agents.models import Agent

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent():
    return Agent.objects.create(slug="echo", name="Echo")


@pytest.fixture
def run(agent):
    run = AgentRun.objects.create(
        agent=agent, label="demo", mode=AgentRun.REVIEW,
        current_step="render", session_link="https://example.com/s",
    )
    spec = AgentRunStep.objects.create(run=run, key="spec", ordinal=0, title="Spec", status=AgentRunStep.COMPLETE)
    render = AgentRunStep.objects.create(run=run, key="render", ordinal=1, title="Render", status=AgentRunStep.RUNNING)
    AgentRunArtifact.objects.create(step=render, name="hero.mp4", url="gs://x", role="walkthrough", size=1024)
    AgentRunVerdict.objects.create(step=render, kind=AgentRunVerdict.QA, passed=True, criteria={"structural": "pass"})
    AgentRunDecision.objects.create(step=spec, question="which persona?", ai_default="flw", status=AgentRunDecision.AI_DEFAULT)
    AgentRunGate.objects.create(step=render)  # open gate
    return run


def test_db_store_satisfies_protocol():
    assert isinstance(DbRunStore(), RunStore)


def test_get_run_hydrates_full_read_model(run):
    store = DbRunStore()
    read = store.get_run("echo", str(run.pk))
    assert read.id == str(run.pk)
    assert read.agent_slug == "echo"
    assert read.label == "demo"
    assert read.mode == "review"
    assert read.session_link == "https://example.com/s"
    # derived status: render is running → in_progress
    assert read.status == "in_progress"
    assert [s.key for s in read.steps] == ["spec", "render"]
    assert len(read.artifacts) == 1 and read.artifacts[0].step_key == "render"
    assert read.artifacts[0].size == 1024
    assert len(read.verdicts) == 1 and read.verdicts[0].passed is True
    assert read.verdicts[0].criteria == {"structural": "pass"}
    assert len(read.decisions) == 1 and read.decisions[0].step_key == "spec"
    assert len(read.gates) == 1 and read.gates[0].is_open is True


def test_get_run_complete_when_all_terminal(agent):
    run = AgentRun.objects.create(agent=agent, label="done")
    AgentRunStep.objects.create(run=run, key="a", ordinal=0, status=AgentRunStep.COMPLETE)
    AgentRunStep.objects.create(run=run, key="b", ordinal=1, status=AgentRunStep.SKIPPED)
    read = DbRunStore().get_run("echo", str(run.pk))
    assert read.status == "complete"


def test_list_runs_returns_summaries(run, agent):
    AgentRun.objects.create(agent=agent, label="second")
    summaries = DbRunStore().list_runs("echo")
    assert len(summaries) == 2
    labels = {s.label for s in summaries}
    assert labels == {"demo", "second"}


def test_list_steps_artifacts_verdicts(run):
    store = DbRunStore()
    rid = str(run.pk)
    assert [s.key for s in store.list_steps("echo", rid)] == ["spec", "render"]
    assert len(store.list_artifacts("echo", rid)) == 1
    assert store.list_artifacts("echo", rid, step_key="spec") == []
    assert len(store.list_verdicts("echo", rid)) == 1


def test_record_gate_closes_it(run):
    store = DbRunStore()
    rid = str(run.pk)
    gate = store.record_gate("echo", rid, "render", decision="approve", decided_by="jj@x.com", note="lgtm")
    assert gate.is_open is False
    assert gate.decision == "approve"
    # re-read
    read = store.get_run("echo", rid)
    assert read.gates[0].decided_at is not None
    assert read.gates[0].decided_by == "jj@x.com"


def test_forked_from_is_carried(agent):
    parent = AgentRun.objects.create(agent=agent, label="parent")
    child = AgentRun.objects.create(agent=agent, label="child", forked_from=parent)
    read = DbRunStore().get_run("echo", str(child.pk))
    assert read.forked_from == str(parent.pk)


def test_fork_not_implemented(run):
    with pytest.raises(NotImplementedError):
        DbRunStore().fork("echo", str(run.pk), at_step="render")


def test_changed_ids(run):
    ids, cursor = DbRunStore().changed_ids("echo")
    assert str(run.pk) in ids
    assert cursor
