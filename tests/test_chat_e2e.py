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

from apps.chat import services as chat
from apps.chat.routing import websocket_urlpatterns as chat_ws
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


async def test_anonymous_chat_socket_rejected_through_stack():
    def setup():
        _owner, session = _seed()
        return session

    session = await database_sync_to_async(setup)()
    comm = WebsocketCommunicator(_ws_app(), f"/ws/chat/{session.id}/")
    connected, code = await comm.connect()
    assert connected is False
    assert code == 4001
