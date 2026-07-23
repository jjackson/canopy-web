"""SP3 — authenticated end-to-end through the ASSEMBLED websocket stack.

Drives the real RealtimeAuthMiddleware -> URLRouter (realtime + chat routes) ->
SessionConsumer with a genuine session cookie: cookie->user auth + routing +
access gate + session snapshot, in-process.
"""
from __future__ import annotations

from importlib import import_module

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth.models import User

from apps.canopy_sessions import services as chat
from apps.canopy_sessions.routing import websocket_urlpatterns as chat_ws
from apps.realtime.channels_auth import RealtimeAuthMiddleware
from apps.realtime.routing import websocket_urlpatterns as realtime_ws
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db(transaction=True)


def _ws_app():
    return RealtimeAuthMiddleware(URLRouter(realtime_ws + chat_ws))


def _make_session_cookie(user):
    from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY

    engine = import_module(settings.SESSION_ENGINE)
    s = engine.SessionStore()
    s[SESSION_KEY] = str(user.pk)
    s[HASH_SESSION_KEY] = user.get_session_auth_hash()
    s[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    s.save()
    return [(b"cookie", f"{settings.SESSION_COOKIE_NAME}={s.session_key}".encode())]


def _seed():
    owner = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=owner)
    WorkspaceMembership.objects.create(user=owner, workspace=ws, role=WorkspaceMembership.OWNER)
    session = chat.create_session(workspace=ws, created_by=owner)
    return owner, session


async def test_authenticated_chat_socket_connects_and_snapshots():
    def setup():
        owner, session = _seed()
        return session, _make_session_cookie(owner)

    session, headers = await database_sync_to_async(setup)()
    comm = WebsocketCommunicator(_ws_app(), f"/ws/chat/{session.id}/", headers=headers)
    connected, _ = await comm.connect()
    assert connected is True
    # first frame is the session snapshot
    for _ in range(4):
        frame = await comm.receive_json_from(timeout=2)
        if frame.get("event") == "session.state":
            assert any(p["role"] == "owner" for p in frame["data"]["participants"])
            break
    else:
        raise AssertionError("no session.state frame")
    await comm.disconnect()


async def _recv_until(comm, event, tries=18):
    for _ in range(tries):
        f = await comm.receive_json_from(timeout=2)
        if f.get("event") == event:
            return f
    raise AssertionError(f"no {event} frame")


async def test_canonical_round_trip():
    """connect -> canonical session.state -> draft.update -> chat.send ->
    draft.committed -> chat.stream_start -> chat.stream_complete, all through the
    assembled RealtimeAuthMiddleware -> URLRouter -> SessionConsumer stack."""
    def setup():
        owner, session = _seed()
        return session, _make_session_cookie(owner), owner.pk

    session, headers, uid = await database_sync_to_async(setup)()
    comm = WebsocketCommunicator(_ws_app(), f"/ws/chat/{session.id}/", headers=headers)
    assert (await comm.connect())[0]
    snap = await _recv_until(comm, "session.state")
    assert snap["data"]["current_user_id"] == uid
    await comm.send_json_to({"action": "draft.update", "data": {"version": 0, "body": "hi there"}})
    await _recv_until(comm, "draft.updated")
    await comm.send_json_to({"action": "chat.send", "data": {}})
    # The stub executes inline, so stream frames and the draft.committed/cleared
    # frames can interleave — assert on the drained SET, not on arrival order.
    seen = {}
    for _ in range(24):
        f = await comm.receive_json_from(timeout=2)
        seen[f["event"]] = f["data"]
        if {"draft.committed", "chat.stream_complete"} <= set(seen):
            break
    assert {"draft.committed", "chat.stream_start", "chat.stream_complete"} <= set(seen)
    assert "plaintext" in seen["chat.stream_complete"]
    await comm.disconnect()


async def test_anonymous_chat_socket_rejected_through_stack():
    def setup():
        _owner, session = _seed()
        return session

    session = await database_sync_to_async(setup)()
    comm = WebsocketCommunicator(_ws_app(), f"/ws/chat/{session.id}/")
    connected, code = await comm.connect()
    assert connected is False
    assert code == 4001
