"""SP2a Task 3 — send_message enqueues a Turn; the ledger projects into Messages."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.agents.models import Agent
from apps.chat import services as chat
from apps.chat.models import Session
from apps.harness import services as harness
from apps.harness.models import Turn
from apps.workspaces.models import Workspace

pytestmark = pytest.mark.django_db(transaction=True)


def _ctx():
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=user)
    agent = Agent.objects.create(slug="echo", name="Echo", workspace=ws, owner=user)
    session = chat.create_session(workspace=ws, created_by=user, agent=agent)
    return user, ws, agent, session


def test_send_creates_user_message_and_queued_turn():
    user, _ws, _agent, session = _ctx()
    msg, turn = chat.send_message(session=session, text="hello", user=user)
    assert msg.role == Session.objects.get(pk=session.pk).messages.first().role == "user"
    assert msg.turn_index == 0
    assert msg.plaintext == "hello"
    assert turn.chat_session_id == session.id
    assert turn.status == Turn.QUEUED
    assert turn.prompt == "hello"


def test_distinct_sends_make_distinct_turns():
    user, _ws, _agent, session = _ctx()
    _m, turn1 = chat.send_message(session=session, text="hi", user=user)
    # A second, genuinely different send is a NEW index -> a new turn.
    _m2, turn2 = chat.send_message(session=session, text="again", user=user)
    assert turn1.id != turn2.id


def test_send_with_client_nonce_is_idempotent():
    user, _ws, _agent, session = _ctx()
    m1, turn1 = chat.send_message(session=session, text="hi", user=user, client_id="nonce-1")
    # A retry with the SAME nonce collapses onto the same Message + Turn.
    m2, turn2 = chat.send_message(session=session, text="hi", user=user, client_id="nonce-1")
    assert m1.id == m2.id
    assert turn1.id == turn2.id
    assert session.messages.filter(role="user").count() == 1


def test_projection_materializes_assistant_events():
    user, _ws, _agent, session = _ctx()
    _msg, turn = chat.send_message(session=session, text="hello", user=user)
    harness.append_events(turn, [{"kind": "assistant", "payload": {"text": "hi there"}}])
    rows = list(session.messages.order_by("turn_index"))
    assert [m.role for m in rows] == ["user", "assistant"]
    assert rows[1].plaintext == "hi there"
    assert rows[1].turn_id == turn.id


def test_projection_maps_tool_events_and_is_idempotent():
    user, _ws, _agent, session = _ctx()
    _msg, turn = chat.send_message(session=session, text="do it", user=user)
    harness.append_events(
        turn,
        [
            {"kind": "tool_start", "payload": {"name": "grep"}},
            {"kind": "tool_end", "payload": {"result": "ok"}},
            {"kind": "assistant", "payload": {"text": "done"}},
        ],
    )
    roles = [m.role for m in session.messages.order_by("turn_index")]
    assert roles == ["user", "tool_use", "tool_result", "assistant"]

    # Re-projecting the same ledger rows creates nothing new (idempotent per seq).
    before = session.messages.count()
    chat.project_events(turn, list(turn.events.all()))
    assert session.messages.count() == before


def test_status_events_are_not_transcript_rows():
    user, _ws, _agent, session = _ctx()
    _msg, turn = chat.send_message(session=session, text="hi", user=user)
    harness.append_events(turn, [{"kind": "status", "payload": {"status": "running"}}])
    # Only the user message exists; status is not a transcript row.
    assert [m.role for m in session.messages.all()] == ["user"]
