"""SP2a Task 2 — harness Turn gains a chat_session target + per-session lock."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError

from apps.agents.models import Agent
from apps.chat.models import Session
from apps.harness import services
from apps.harness.models import Turn
from apps.workspaces.models import Workspace

pytestmark = pytest.mark.django_db


def _ws_user():
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=user)
    return ws, user


def _session(ws, user, agent=None):
    return Session.objects.create(workspace=ws, agent=agent, created_by=user)


def test_enqueue_session_turn():
    ws, user = _ws_user()
    s = _session(ws, user)
    turn, created = services.enqueue_turn(
        session=s, origin=Turn.ORIGIN_API, idempotency_key="k1", prompt="hi"
    )
    assert created is True
    assert turn.chat_session_id == s.id
    assert turn.agent_id is None
    assert turn.project == ""
    assert turn.workspace_id is None  # tenancy derives from the session


def test_enqueue_rejects_multiple_targets():
    ws, user = _ws_user()
    s = _session(ws, user)
    agent = Agent.objects.create(slug="echo", name="Echo", workspace=ws)
    with pytest.raises(ValueError):
        services.enqueue_turn(agent=agent, session=s, origin=Turn.ORIGIN_API, idempotency_key="k")


def test_enqueue_rejects_no_target():
    with pytest.raises(ValueError):
        services.enqueue_turn(origin=Turn.ORIGIN_API, idempotency_key="k")


def test_one_executing_turn_per_session():
    ws, user = _ws_user()
    s = _session(ws, user)
    Turn.objects.create(
        chat_session=s, origin=Turn.ORIGIN_API, idempotency_key="k1", status=Turn.RUNNING
    )
    with pytest.raises(IntegrityError):
        Turn.objects.create(
            chat_session=s, origin=Turn.ORIGIN_API, idempotency_key="k2", status=Turn.CLAIMED
        )


def test_two_sessions_execute_in_parallel():
    ws, user = _ws_user()
    s1, s2 = _session(ws, user), _session(ws, user)
    Turn.objects.create(
        chat_session=s1, origin=Turn.ORIGIN_API, idempotency_key="k1", status=Turn.RUNNING
    )
    # Different session — the per-session lock does not block it.
    Turn.objects.create(
        chat_session=s2, origin=Turn.ORIGIN_API, idempotency_key="k2", status=Turn.RUNNING
    )


def test_target_property_prefers_session_agent():
    ws, user = _ws_user()
    agent = Agent.objects.create(slug="echo", name="Echo", workspace=ws)
    s = _session(ws, user, agent=agent)
    t = Turn.objects.create(chat_session=s, origin=Turn.ORIGIN_API, idempotency_key="k")
    assert t.target == "echo"


def test_check_constraint_rejects_agent_plus_session():
    ws, user = _ws_user()
    agent = Agent.objects.create(slug="echo", name="Echo", workspace=ws)
    s = _session(ws, user)
    with pytest.raises(IntegrityError):
        Turn.objects.create(
            agent=agent, chat_session=s, origin=Turn.ORIGIN_API, idempotency_key="k"
        )


def test_session_turn_target_falls_back_to_project():
    ws, user = _ws_user()
    s = Session.objects.create(workspace=ws, created_by=user, project="canopy-web")
    turn, _ = services.enqueue_turn(
        session=s, origin=Turn.ORIGIN_API, idempotency_key="proj1", prompt="hi"
    )
    assert turn.target == "canopy-web"  # not the session:<hex> marker
