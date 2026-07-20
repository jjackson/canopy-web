"""Runner readiness: the 'can I fire a turn' signal, distinct from being online."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from apps.harness.models import Runner
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


def _runner(user, ws):
    return Runner.objects.create(
        name="mbp", kind=Runner.EMDASH, host="h", paired_by=user, workspace=ws,
        status=Runner.ONLINE, last_heartbeat_at=timezone.now(),
    )


@pytest.fixture
def user(db):
    return User.objects.create_user("jj", "jj@dimagi.com", "pw")


@pytest.fixture
def ws(db, user):
    w = Workspace.objects.create(slug="dimagi", display_name="Dimagi", created_by=user)
    WorkspaceMembership.objects.create(user=user, workspace=w, role=WorkspaceMembership.OWNER)
    return w


def test_runner_defaults_to_ready(user, ws):
    r = _runner(user, ws)
    assert r.ready is True
    assert r.ready_note == ""


def test_heartbeat_persists_not_ready_with_a_reason(user, ws):
    r = _runner(user, ws)
    c = Client()
    c.force_login(user)
    resp = c.post(
        f"/api/harness/runners/{r.id}/heartbeat",
        {"active_turn_ids": [], "ready": False, "ready_note": "Not logged in"},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["ready"] is False
    assert body["ready_note"] == "Not logged in"
    r.refresh_from_db()
    assert r.ready is False and r.ready_note == "Not logged in"


def test_heartbeat_omitting_ready_defaults_to_ready_true(user, ws):
    """An older runner that predates the field still heartbeats — it must read as
    ready (fail OPEN: an un-upgraded runner is presumed able to fire, as today)."""
    r = _runner(user, ws)
    Runner.objects.filter(pk=r.pk).update(ready=False, ready_note="stale")
    c = Client()
    c.force_login(user)
    c.post(f"/api/harness/runners/{r.id}/heartbeat", {"active_turn_ids": []},
           content_type="application/json")
    r.refresh_from_db()
    assert r.ready is True and r.ready_note == ""
