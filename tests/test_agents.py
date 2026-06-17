"""Tests for the agent workspace services (idempotency, catalog replace)."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from apps.agents import services
from apps.agents.models import Agent, AgentSkill, AgentSync, AgentTask, AgentWorkProduct

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


def test_sync_tasks_replaces_board_and_normalizes_status():
    agent = _agent()
    link = SimpleNamespace(model_dump=lambda: {"label": "doc", "url": "https://d/1"})
    tasks = [
        SimpleNamespace(ext_id="t1", title="Ship PRIDE guide", status="in_progress", priority="high",
                        owner="Sarvesh", due=dt.date(2026, 6, 20), links=[link], notes="", position=0, source="sheet"),
        SimpleNamespace(ext_id="t2", title="Weird status", status="banana", priority="", owner="",
                        due=None, links=[], notes="", position=1, source="sheet"),
    ]
    assert services.sync_tasks(agent, tasks) == {"count": 2}
    assert AgentTask.objects.get(agent=agent, ext_id="t2").status == "todo"  # normalized
    assert AgentTask.objects.get(agent=agent, ext_id="t1").links == [{"label": "doc", "url": "https://d/1"}]
    # re-sync with fewer tasks replaces the whole board
    assert services.sync_tasks(agent, tasks[:1]) == {"count": 1}
    assert AgentTask.objects.filter(agent=agent).count() == 1
