"""Tests for the agent workspace services (idempotency, catalog replace)."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from apps.agent_runs.models import AgentRun, AgentRunGate, AgentRunStep
from apps.agents import services
from apps.agents.models import Agent, AgentSkill, AgentSync, AgentTask, AgentTurn, AgentWorkProduct

pytestmark = pytest.mark.django_db


def _agent(slug="echo"):
    return services.upsert_agent(
        SimpleNamespace(slug=slug, name="Echo", description="", persona="", email="echo@x.com", avatar_url="")
    )


def test_upsert_agent_is_idempotent_by_slug():
    a1 = _agent()
    a2 = services.upsert_agent(
        SimpleNamespace(slug="echo", name="Echo v2", description="d", persona="p", email="", avatar_url="")
    )
    assert a1.pk == a2.pk
    assert Agent.objects.count() == 1
    assert Agent.objects.get(slug="echo").name == "Echo v2"


def test_sync_is_idempotent_per_period_and_source():
    agent = _agent()
    start = dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc)
    end = dt.datetime(2026, 6, 17, tzinfo=dt.timezone.utc)
    payload = SimpleNamespace(
        period_start=start, period_end=end, title="Sync 1", summary="s",
        doc_url="https://docs.google.com/document/d/abc/edit",
        self_grades={"work": "C+", "skills": "B-"}, source="manager-sync",
    )
    services.upsert_sync(agent, payload)
    payload.title = "Sync 1 (revised)"
    services.upsert_sync(agent, payload)  # same window+source → replaces
    assert AgentSync.objects.filter(agent=agent).count() == 1
    assert AgentSync.objects.get(agent=agent).title == "Sync 1 (revised)"
    assert AgentSync.objects.get(agent=agent).self_grades["work"] == "C+"


def _turn(**kw):
    base = dict(cli_session_id="sess-1", title="Turn 1", summary="did stuff",
                task_ext_ids=["t1"], work_product_urls=[], session_slug="", share_token="",
                started_at=None, ended_at=None, source="turn")
    base.update(kw)
    return SimpleNamespace(**base)


def test_turn_is_idempotent_per_cli_session_id():
    agent = _agent()
    services.upsert_turn(agent, _turn(title="Turn 1", task_ext_ids=["t1"]))
    # re-package the same session (e.g. after the transcript uploads) → updates in place
    services.upsert_turn(agent, _turn(title="Turn 1 (transcript added)",
                                      task_ext_ids=["t1", "t2"],
                                      session_slug="abc123", share_token="tok999"))
    assert AgentTurn.objects.filter(agent=agent).count() == 1
    turn = AgentTurn.objects.get(agent=agent)
    assert turn.title == "Turn 1 (transcript added)"
    assert turn.task_ext_ids == ["t1", "t2"]
    assert turn.share_token == "tok999"
    # a different session is a separate turn
    services.upsert_turn(agent, _turn(cli_session_id="sess-2", title="Turn 2"))
    assert AgentTurn.objects.filter(agent=agent).count() == 2


def test_turn_transcript_is_optional():
    agent = _agent()
    turn = services.upsert_turn(agent, _turn(session_slug="", share_token=""))
    assert turn.session_slug == "" and turn.share_token == ""
    assert turn.task_ext_ids == ["t1"]  # the unit of work is still packaged


def test_agent_detail_counts_turns():
    agent = _agent()
    assert services.agent_detail(agent)["turn_count"] == 0
    assert services.agent_detail(agent)["latest_turn_at"] is None
    services.upsert_turn(agent, _turn(cli_session_id="s1"))
    services.upsert_turn(agent, _turn(cli_session_id="s2"))
    detail = services.agent_detail(agent)
    assert detail["turn_count"] == 2
    assert detail["latest_turn_at"] is not None


def test_work_products_upsert_by_url():
    agent = _agent()
    items = [SimpleNamespace(title="Story", kind="doc", url="https://d/1", description="", tags=["x"], source="echo")]
    assert services.upsert_work_products(agent, items) == {"created": 1, "replaced": 0}
    items[0].title = "Story v2"
    assert services.upsert_work_products(agent, items) == {"created": 0, "replaced": 1}
    assert AgentWorkProduct.objects.get(agent=agent).title == "Story v2"


def test_replace_skills_mirrors_catalog():
    agent = _agent()
    services.replace_skills(agent, [
        SimpleNamespace(name="email-communicator", description="email", url="u1", improvement_note=""),
        SimpleNamespace(name="story-draft", description="write", url="u2", improvement_note="fixed slop"),
    ])
    assert agent.skills.count() == 2
    services.replace_skills(agent, [
        SimpleNamespace(name="email-communicator", description="email v2", url="u1", improvement_note=""),
    ])
    assert agent.skills.count() == 1
    assert AgentSkill.objects.get(agent=agent).description == "email v2"


def _task(**kw):
    base = dict(ext_id="t", title="T", next_action="", status="suggested", owner="",
                assigned="", confidence="", rationale="", source_url="", plan="",
                due=None, links=[], notes="", position=0, source="sheet")
    base.update(kw)
    return SimpleNamespace(**base)


def test_sync_tasks_upserts_and_normalizes_status():
    agent = _agent()
    link = SimpleNamespace(model_dump=lambda: {"label": "doc", "url": "https://d/1"})
    tasks = [
        _task(ext_id="t1", title="PRIDE story", next_action="Run the interview", status="in_progress",
              owner="Sarvesh", assigned="Sarvesh", due=dt.date(2026, 6, 20), links=[link], position=0),
        _task(ext_id="t2", title="Weird status", status="banana", position=1),  # invalid -> suggested
    ]
    res = services.sync_tasks(agent, tasks)
    assert res["count"] == 2 and res["created"] == 2
    assert AgentTask.objects.get(agent=agent, ext_id="t2").status == "suggested"
    assert AgentTask.objects.get(agent=agent, ext_id="t1").assigned == "Sarvesh"
    # re-sync is NON-destructive (DB is the source of truth): updates, never deletes
    tasks[0].title = "PRIDE story v2"
    res2 = services.sync_tasks(agent, tasks[:1])
    assert res2["created"] == 0 and AgentTask.objects.filter(agent=agent).count() == 2
    assert AgentTask.objects.get(agent=agent, ext_id="t1").title == "PRIDE story v2"


def test_needs_you_types_ranks_and_excludes_echo():
    agent = _agent()
    # review: a suggested task — the human must validate/decline it
    services.create_task(agent, _task(ext_id="r1", title="Polio story", status="suggested",
                                      owner="Matt", assigned="Matt", position=0))
    # question: an in-progress task blocked on a human (Echo needs a decision)
    services.create_task(agent, _task(ext_id="q1", title="Cholera story", status="in_progress",
                                      owner="Matt", assigned="Sarvesh", position=1))
    # excluded: in-progress assigned to Echo — Echo has the ball, not the human
    services.create_task(agent, _task(ext_id="e1", title="Backlog upkeep", status="in_progress",
                                      owner="Matt", assigned="Echo", position=2))
    # excluded: a done task is no longer actionable
    services.create_task(agent, _task(ext_id="d1", title="Shipped", status="done", position=3))
    # notify: a recent FYI sync (no gate)
    services.upsert_sync(agent, SimpleNamespace(
        period_start=dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc),
        period_end=dt.datetime(2026, 6, 17, tzinfo=dt.timezone.utc),
        title="Sync 1", summary="", doc_url="https://d/sync", self_grades={}, source="manager-sync"))

    res = services.needs_you(agent)
    pairs = [(i["type"], i["title"]) for i in res["items"]]
    assert pairs[0] == ("review", "Polio story")        # review band leads
    assert ("question", "Cholera story") in pairs
    assert ("notify", "Sync 1") in pairs
    titles = [t for _, t in pairs]
    assert "Backlog upkeep" not in titles               # nothing Echo is working
    assert "Shipped" not in titles                       # nothing done
    rank = {"review": 0, "question": 1, "notify": 2}
    order = [rank[i["type"]] for i in res["items"]]
    assert order == sorted(order)                        # typed bands, ranked
    assert res["waiting_count"] == 2                      # gated (review+question) only


def test_needs_you_projects_run_state():
    """Run lifecycle surfaces on /needs-you reusing review/question/notify
    (spec §5): open gate → review, failed step → question, completed → notify."""
    agent = _agent()
    # Run A: an OPEN gate awaiting a human decision → review (gated/waiting).
    run_a = AgentRun.objects.create(agent=agent, label="Render demo", current_step="render")
    step_a = AgentRunStep.objects.create(run=run_a, key="render", ordinal=0, status=AgentRunStep.RUNNING)
    AgentRunGate.objects.create(step=step_a)  # decided_at None → open
    # Run B: a FAILED step → question (gated/waiting).
    run_b = AgentRun.objects.create(agent=agent, label="Build app", current_step="build")
    AgentRunStep.objects.create(run=run_b, key="build", ordinal=0, status=AgentRunStep.FAILED, error="boom")
    # Run C: all steps terminal → completed run → notify (NOT waiting).
    run_c = AgentRun.objects.create(agent=agent, label="Shipped run")
    AgentRunStep.objects.create(run=run_c, key="done", ordinal=0, status=AgentRunStep.COMPLETE)

    res = services.needs_you(agent)
    triples = [(i["type"], i["ref_kind"], i["title"]) for i in res["items"]]
    assert ("review", "run", "Render demo") in triples          # open gate
    assert ("question", "run", "Build app") in triples           # failed step
    assert ("notify", "run", "Shipped run") in triples           # completed run
    # open gate + failed step are gated → bump the "waiting on you" badge
    assert res["waiting_count"] >= 2
    # the review item's subtitle carries the gate's step
    review_run = next(i for i in res["items"] if i["ref_kind"] == "run" and i["type"] == "review")
    assert "render" in review_run["subtitle"]
    # ranking preserved across the merged task + run bands
    rank = {"review": 0, "question": 1, "notify": 2}
    order = [rank[i["type"]] for i in res["items"]]
    assert order == sorted(order)


def test_agenttask_run_link_round_trips():
    """A task can mean 'execute this run' — the nullable FK round-trips and
    SET_NULL leaves the task when its run is deleted."""
    agent = _agent()
    run = AgentRun.objects.create(agent=agent, label="Linked run")
    task = services.create_task(agent, _task(ext_id="t1", title="Execute the run"))
    assert task.run_id is None                                   # nullable by default
    task.run = run
    task.save(update_fields=["run"])
    task.refresh_from_db()
    assert task.run_id == run.pk and task.run == run
    assert list(run.tasks.all()) == [task]                       # reverse accessor
    run.delete()                                                 # on_delete=SET_NULL
    task.refresh_from_db()
    assert task.run_id is None and AgentTask.objects.filter(pk=task.pk).exists()


def test_command_flow_accept_then_apply_and_decline():
    agent = _agent()
    t = services.create_task(agent, _task(ext_id="t1", title="ZEGCAWIS story", next_action="Get consent",
                                          status="suggested", owner="Matt", confidence="high",
                                          rationale="strong near-miss", plan="email the FLW"))
    # accept: applies to the task AND leaves a pending command for the agent
    cmd = services.create_command(agent, t, "accept", {}, "jonathan@dimagi.com")
    t.refresh_from_db()
    assert t.status == "in_progress" and t.assigned == "Echo"
    assert cmd.status == "pending"
    assert [c.id for c in services.list_commands(agent, "pending")] == [cmd.id]
    services.apply_command(cmd, "drafted")
    cmd.refresh_from_db()
    assert cmd.status == "applied" and cmd.result_note == "drafted"
    # decline applies immediately (terminal) and records the reason
    cmd2 = services.create_command(agent, t, "decline", {"reason": "not now"}, "x")
    t.refresh_from_db()
    assert t.status == "declined" and "not now" in t.notes and cmd2.status == "applied"
