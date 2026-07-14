"""SessionLink — the durable, cross-account thread↔session mapping."""
from __future__ import annotations

import pytest
from django.db import IntegrityError

from apps.agents.models import Agent
from apps.harness import services
from apps.harness.models import Runner, SessionLink

pytestmark = pytest.mark.django_db


def _agent(slug="hal"):
    return Agent.objects.create(slug=slug, name=slug.title())


def _runner(host="jj@mbp", name="r", agents=("hal",)):
    return Runner.objects.create(
        name=name, kind=Runner.EMDASH, capabilities={"agents": list(agents)}, host=host
    )


def test_runner_has_host_field():
    assert _runner(host="jj2@mbp").host == "jj2@mbp"


def test_session_link_unique_per_agent_thread():
    a = _agent()
    SessionLink.objects.create(agent=a, thread_key="t-1")
    with pytest.raises(IntegrityError):
        SessionLink.objects.create(agent=a, thread_key="t-1")


def test_same_thread_different_agent_is_allowed():
    SessionLink.objects.create(agent=_agent("hal"), thread_key="t-1")
    SessionLink.objects.create(agent=_agent("eva"), thread_key="t-1")  # no raise
    assert SessionLink.objects.count() == 2


def test_reusable_by_requires_same_runner_and_host_and_task():
    a = _agent()
    r = _runner(host="jj@mbp")
    other_host = _runner(host="jj2@mbp", name="r2")
    link = SessionLink.objects.create(
        agent=a, thread_key="t-1", live_runner=r, live_host="jj@mbp",
        live_emdash_task_id="etask-1",
    )
    assert link.reusable_by(r) is True
    # same runner row but the host recorded differs from the runner's host → not reusable
    assert link.reusable_by(other_host) is False
    # no emdash task recorded → nothing to reuse
    link.live_emdash_task_id = ""
    assert link.reusable_by(r) is False


def test_resolve_new_thread_returns_no_reuse():
    plan = services.resolve_session(_agent(), "brand-new", _runner())
    assert plan["new_thread"] is True and plan["reuse"] is False and plan["link_id"] is None


def test_resolve_reuse_when_current_runner_owns_live_session():
    a = _agent()
    r = _runner(host="jj@mbp")
    services.record_session(
        a, "t-1", runner=r, emdash_task_id="etask-1", session_id="sess-1",
        agent_task_ext_id="TASK-9", summary="prior context",
    )
    plan = services.resolve_session(a, "t-1", r)
    assert plan["reuse"] is True
    assert plan["emdash_task_id"] == "etask-1"
    assert plan["agent_task_ext_id"] == "TASK-9"


def test_resolve_other_account_falls_back_to_rehydrate():
    """Session created under account A; account B (different host) must NOT reuse the
    live emdash session, but MUST get the durable context to rehydrate a fresh one."""
    a = _agent()
    account_a = _runner(host="jjA@mbp", name="rA")
    account_b = _runner(host="jjB@mbp", name="rB")
    services.record_session(
        a, "t-1", runner=account_a, emdash_task_id="etask-A", session_id="sess-A",
        agent_task_ext_id="TASK-9", summary="what happened so far",
    )
    plan = services.resolve_session(a, "t-1", account_b)
    assert plan["reuse"] is False                      # can't reach account A's emdash
    assert plan["new_thread"] is False                 # but the thread is known
    assert plan["summary"] == "what happened so far"   # context survives the switch
    assert plan["agent_task_ext_id"] == "TASK-9"


def test_record_session_repoints_and_preserves_summary():
    a = _agent()
    rA = _runner(host="jjA@mbp", name="rA")
    rB = _runner(host="jjB@mbp", name="rB")
    services.record_session(a, "t-1", runner=rA, emdash_task_id="etask-A",
                            agent_task_ext_id="TASK-9", summary="ctx")
    # account B takes over the thread; don't pass summary → preserved
    link = services.record_session(a, "t-1", runner=rB, emdash_task_id="etask-B")
    assert link.live_runner_id == rB.id and link.live_host == "jjB@mbp"
    assert link.live_emdash_task_id == "etask-B"
    assert link.summary == "ctx"                # preserved (not overwritten with "")
    assert link.agent_task_ext_id == "TASK-9"   # preserved
    assert SessionLink.objects.count() == 1     # upsert, not duplicate
