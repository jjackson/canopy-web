"""SP3 Task 3 — the per-session multiplayer SessionConsumer.

Two sockets on one session: a draft edit by one is broadcast to the other, and a
commit sends + streams the assistant response to everyone (the stub executes).
"""
from __future__ import annotations

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser, User

from apps.agents.models import Agent
from apps.chat import services as chat
from apps.chat.consumers import SessionConsumer
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db(transaction=True)


def _seed():
    owner = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=owner)
    WorkspaceMembership.objects.create(user=owner, workspace=ws, role=WorkspaceMembership.OWNER)
    teammate = User.objects.create_user("t", "t@dimagi.com", "pw")
    WorkspaceMembership.objects.create(user=teammate, workspace=ws, role=WorkspaceMembership.EDITOR)
    agent = Agent.objects.create(slug="echo", name="Echo", workspace=ws, owner=owner)
    session = chat.create_session(workspace=ws, created_by=owner, agent=agent)
    return owner, teammate, session


async def _connect(session, user):
    comm = WebsocketCommunicator(SessionConsumer.as_asgi(), f"/ws/chat/{session.id}/")
    comm.scope["user"] = user
    comm.scope["url_route"] = {"kwargs": {"session_id": str(session.id)}}
    return comm


async def _recv_match(comm, pred, tries=14):
    for _ in range(tries):
        frame = await comm.receive_json_from(timeout=2)
        if pred(frame):
            return frame
    raise AssertionError("expected frame not received")


async def test_anonymous_rejected():
    _o, _t, session = await database_sync_to_async(_seed)()
    comm = await _connect(session, AnonymousUser())
    connected, code = await comm.connect()
    assert connected is False
    assert code == 4001


async def test_non_member_rejected():
    _o, _t, session = await database_sync_to_async(_seed)()
    outsider = await database_sync_to_async(User.objects.create_user)("no", "no@dimagi.com", "pw")
    comm = await _connect(session, outsider)
    connected, code = await comm.connect()
    assert connected is False
    assert code == 4003


async def test_member_gets_session_snapshot():
    owner, _t, session = await database_sync_to_async(_seed)()
    comm = await _connect(session, owner)
    connected, _ = await comm.connect()
    assert connected is True
    snap = await _recv_match(comm, lambda f: f.get("event") == "session.state")
    roles = {p["role"] for p in snap["data"]["participants"]}
    assert "owner" in roles
    await comm.disconnect()


async def test_draft_update_broadcasts_to_other_socket():
    owner, teammate, session = await database_sync_to_async(_seed)()
    a = await _connect(session, owner)
    assert (await a.connect())[0]
    b = await _connect(session, teammate)
    assert (await b.connect())[0]

    await a.send_json_to({"action": "draft.update", "data": {"expected_version": 0, "body": "hello team"}})
    frame = await _recv_match(b, lambda f: f.get("event") == "draft.updated")
    assert frame["data"]["body"] == "hello team"
    assert frame["data"]["last_editor"] == owner.id
    await a.disconnect()
    await b.disconnect()


async def test_commit_sends_and_streams_assistant_to_all():
    owner, teammate, session = await database_sync_to_async(_seed)()
    a = await _connect(session, owner)
    assert (await a.connect())[0]
    b = await _connect(session, teammate)
    assert (await b.connect())[0]

    await a.send_json_to({"action": "draft.update", "data": {"expected_version": 0, "body": "do it"}})
    await _recv_match(a, lambda f: f.get("event") == "draft.updated")
    await a.send_json_to({"action": "draft.commit"})

    # Both sockets see the streamed assistant turn event (the stub executed).
    is_assistant = lambda f: f.get("event") == "chat.turn_event" and f["data"].get("kind") == "assistant"
    assert await _recv_match(a, is_assistant)
    assert await _recv_match(b, is_assistant)

    # And the durable transcript has the user + assistant messages.
    roles = await database_sync_to_async(
        lambda: [m.role for m in session.messages.order_by("turn_index")]
    )()
    assert roles == ["user", "assistant"]
    await a.disconnect()
    await b.disconnect()
