"""SP1 Task 5 — RealtimeAuthMiddleware resolves scope['user'].

Anonymous by default; from a session cookie; from a Bearer PAT. DB reads inside
the middleware go through database_sync_to_async — if sqlite :memory: rows aren't
visible from that executor, the bearer/session tests fail (and we switch those
tests to a shared-cache DB).
"""
from __future__ import annotations

from importlib import import_module

import pytest
from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth.models import User

from apps.realtime.channels_auth import RealtimeAuthMiddleware
from apps.tokens.models import PersonalToken

pytestmark = pytest.mark.django_db(transaction=True)


async def _run_mw(scope):
    holder: dict = {}

    async def app(s, receive, send):
        holder["user"] = s["user"]

    await RealtimeAuthMiddleware(app)(scope, None, None)
    return holder["user"]


def _make_session(user) -> str:
    from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY

    engine = import_module(settings.SESSION_ENGINE)
    session = engine.SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session.save()
    return session.session_key


async def test_anonymous_when_no_creds():
    user = await _run_mw({"type": "websocket", "headers": []})
    assert user.is_authenticated is False


async def test_resolves_from_bearer():
    u = await database_sync_to_async(User.objects.create_user)("jj", "jj@dimagi.com", "pw")
    raw, _tok = await database_sync_to_async(PersonalToken.create_for_user)(user=u, label="t")
    scope = {"type": "websocket", "headers": [(b"authorization", f"Bearer {raw}".encode())]}
    user = await _run_mw(scope)
    assert user.is_authenticated
    assert user.pk == u.pk


async def test_resolves_from_session_cookie():
    u = await database_sync_to_async(User.objects.create_user)("jj", "jj@dimagi.com", "pw")
    key = await database_sync_to_async(_make_session)(u)
    cookie = f"{settings.SESSION_COOKIE_NAME}={key}".encode()
    user = await _run_mw({"type": "websocket", "headers": [(b"cookie", cookie)]})
    assert user.is_authenticated
    assert user.pk == u.pk


async def test_session_without_auth_hash_is_anonymous():
    # A session missing the auth hash (e.g. one a password change invalidated)
    # must not authenticate over WS, matching django.contrib.auth.get_user.
    u = await database_sync_to_async(User.objects.create_user)("jj", "jj@dimagi.com", "pw")

    def mk():
        from django.contrib.auth import SESSION_KEY

        engine = import_module(settings.SESSION_ENGINE)
        session = engine.SessionStore()
        session[SESSION_KEY] = str(u.pk)  # deliberately no HASH_SESSION_KEY
        session.save()
        return session.session_key

    key = await database_sync_to_async(mk)()
    cookie = f"{settings.SESSION_COOKIE_NAME}={key}".encode()
    user = await _run_mw({"type": "websocket", "headers": [(b"cookie", cookie)]})
    assert user.is_authenticated is False


async def test_bad_bearer_is_anonymous():
    scope = {"type": "websocket", "headers": [(b"authorization", b"Bearer not-a-real-token")]}
    user = await _run_mw(scope)
    assert user.is_authenticated is False
