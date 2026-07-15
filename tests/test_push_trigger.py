"""The trigger. needs_you() is an aggregation with no single event to hang a push
on, so we snapshot waiting_count per agent and push only when it INCREASES."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User

from apps.agents.models import Agent, AgentTask
from apps.push.models import AgentWaitingSnapshot, PushSubscription
from apps.workspaces.models import Workspace, WorkspaceMembership


# transaction=True is load-bearing, not decorative: mark_dirty() relies on
# transaction.on_commit() to coalesce a bulk sync into one push per agent. Under
# the plain @pytest.mark.django_db marker, pytest-django wraps each test in an
# outer atomic() that is rolled back (never committed) at teardown, so
# on_commit callbacks registered during the test are silently discarded and
# EVERY assertion below that expects a push would fail with call_count == 0.
# transaction=True runs the test against a real (uncommitted-wrapper-free)
# connection, so on_commit fires as it would in production. Verified via a
# throwaway diagnostic test before making this change.
pytestmark = pytest.mark.django_db(transaction=True)


# apps.push.services._dirty is process-global by design (see the module
# docstring's note on it — coalescing, not per-connection). That means any
# OTHER test anywhere in this suite that saves an AgentTask/AgentRunGate/
# AgentRunStep under the plain (non-transaction=True) django_db marker calls
# mark_dirty(), registers an on_commit that its rolled-back test transaction
# never fires, and leaves that agent id sitting in _dirty forever. The next
# mark_dirty() call anywhere in the process then sees `not _dirty` as False
# and skips registering its OWN on_commit — so this file's assertions would
# silently see call_count == 0 depending on what ran earlier in the session.
# Verified by reproducing it with a single unrelated AgentTask-creating test
# run before this file. Reset the set around every test so these tests are
# self-contained regardless of suite order; this does not touch the
# production module — see the report for the underlying fragility.
@pytest.fixture(autouse=True)
def _reset_dirty_set():
    from apps.push import services

    services._dirty.clear()
    yield
    services._dirty.clear()


# _send_one is mocked in every test below, so no real push ever goes over the
# wire — but send_to_user() intentionally short-circuits BEFORE ever calling
# it when settings.VAPID_PRIVATE_KEY is empty ("push not configured — stay
# silent rather than raise"). Locally that key comes from .env; any
# environment without it (CI, or this suite run with .env moved aside per the
# task brief) has it unset, so every push-expecting assertion here would
# silently see call_count == 0 for a reason that has nothing to do with the
# trigger logic under test. Confirmed by running the suite with .env moved
# aside before adding this override. Production behavior (the guard itself)
# is untouched — this only sets a dummy key for the test process.
@pytest.fixture(autouse=True)
def _vapid_configured(settings):
    settings.VAPID_PRIVATE_KEY = "test-vapid-private-key"
    settings.VAPID_SUBJECT = "mailto:test@example.com"


@pytest.fixture()
def user():
    return User.objects.create_user("jj", "jj@dimagi.com", "pw")


@pytest.fixture()
def workspace(user):
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=user)
    WorkspaceMembership.objects.create(user=user, workspace=ws, role=WorkspaceMembership.OWNER)
    return ws


# owner is load-bearing: refresh_agent_waiting pushes to agent.owner, and
# Agent.owner is nullable (apps/agents/models.py:23). An ownerless agent pushes
# to nobody — so a fixture without it would make every assertion below pass
# vacuously.
@pytest.fixture()
def agent(workspace, user):
    return Agent.objects.create(slug="echo", name="Echo", workspace=workspace, owner=user)


@pytest.fixture()
def sub(user):
    return PushSubscription.objects.create(
        user=user, endpoint="https://fcm.googleapis.com/fcm/send/AAA", p256dh="k", auth="a"
    )


def _task(agent, ext_id, status="suggested"):
    return AgentTask.objects.create(agent=agent, ext_id=ext_id, title=f"T {ext_id}", status=status)


def test_a_new_suggested_task_pushes(agent, sub):
    with patch("apps.push.services._send_one") as send:
        _task(agent, "t1")
    assert send.call_count == 1
    assert AgentWaitingSnapshot.objects.get(agent=agent).waiting_count == 1


def test_clearing_an_item_does_not_push(agent, sub):
    """The count going DOWN must be silent — being buzzed when you clear
    something is the fastest way to make someone turn notifications off."""
    t = _task(agent, "t1")
    with patch("apps.push.services._send_one") as send:
        t.status = AgentTask.DECLINED
        t.save()
    assert send.call_count == 0
    assert AgentWaitingSnapshot.objects.get(agent=agent).waiting_count == 0


def test_an_unchanged_count_does_not_push(agent, sub):
    _task(agent, "t1")
    t2 = _task(agent, "t2", status="done")
    with patch("apps.push.services._send_one") as send:
        t2.title = "renamed, still done"
        t2.save()
    assert send.call_count == 0


def test_a_bulk_sync_pushes_once_per_agent_not_once_per_row(agent, sub):
    """THE storm case: POST /tasks/sync upserts many rows in one transaction.
    Without the on_commit dirty-set this is one push per row."""
    from django.db import transaction

    with patch("apps.push.services._send_one") as send:
        with transaction.atomic():
            for i in range(10):
                _task(agent, f"bulk{i}")
    assert send.call_count == 1
    assert AgentWaitingSnapshot.objects.get(agent=agent).waiting_count == 10


def test_two_agents_in_one_transaction_push_once_each(agent, workspace, user, sub):
    from django.db import transaction

    hal = Agent.objects.create(slug="hal", name="Hal", workspace=workspace, owner=user)
    with patch("apps.push.services._send_one") as send:
        with transaction.atomic():
            _task(agent, "a1")
            _task(hal, "h1")
    assert send.call_count == 2


def test_an_open_run_gate_pushes(agent, sub):
    """Gates reach the agent through TWO hops — gate.step.run.agent_id. An earlier
    draft of this plan used gate.run (which does not exist) behind a getattr
    guard: mark_dirty would never fire, NO gate would ever push, and every
    task-only test above would still pass. This is the test that catches that.

    A gate with no decision recorded is open (services._run_inbox_items reads
    gate.is_open), and an open gate is a 'review' item — so waiting_count rises.
    """
    from apps.agent_runs.models import AgentRun, AgentRunGate, AgentRunStep

    run = AgentRun.objects.create(agent=agent)
    step = AgentRunStep.objects.create(run=run, key="build")
    with patch("apps.push.services._send_one") as send:
        AgentRunGate.objects.create(step=step)  # no decision == awaiting a human
    assert send.call_count == 1
    assert AgentWaitingSnapshot.objects.get(agent=agent).waiting_count == 1


def test_deciding_a_gate_does_not_push(agent, sub):
    """Closing a gate lowers the count. Silence, same as clearing a task."""
    from apps.agent_runs.models import AgentRun, AgentRunGate, AgentRunStep

    run = AgentRun.objects.create(agent=agent)
    step = AgentRunStep.objects.create(run=run, key="build")
    gate = AgentRunGate.objects.create(step=step)
    with patch("apps.push.services._send_one") as send:
        gate.decision = "approved"
        gate.save()
    assert send.call_count == 0


def test_a_user_with_no_subscription_gets_nothing(agent):
    with patch("apps.push.services._send_one") as send:
        _task(agent, "t1")
    assert send.call_count == 0
    # The snapshot still advances — otherwise the first push after subscribing
    # would fire for items that were already there.
    assert AgentWaitingSnapshot.objects.get(agent=agent).waiting_count == 1


def test_a_dead_subscription_is_pruned(agent, sub):
    """A subscription dies silently when the app is uninstalled: the push service
    starts returning 410 Gone. Prune on that signal, not on a timer."""
    from pywebpush import WebPushException

    class _Resp:
        status_code = 410

    with patch("apps.push.services._send_one", side_effect=WebPushException("gone", response=_Resp())):
        _task(agent, "t1")
    assert not PushSubscription.objects.filter(pk=sub.pk).exists()


def test_a_transient_send_failure_keeps_the_subscription(agent, sub):
    from pywebpush import WebPushException

    class _Resp:
        status_code = 503

    with patch("apps.push.services._send_one", side_effect=WebPushException("busy", response=_Resp())):
        _task(agent, "t1")
    sub.refresh_from_db()
    assert sub.failure_count == 1  # kept — a 503 is the service's problem, not ours
