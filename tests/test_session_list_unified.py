import datetime as dt
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from apps.canopy_sessions.models import RunnerBinding, Session
from apps.harness.models import Runner
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


def _ctx():
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="w1", display_name="W1", created_by=user)
    WorkspaceMembership.objects.create(user=user, workspace=ws, role=WorkspaceMembership.OWNER)
    c = Client(); c.force_login(user)
    return user, ws, c


def test_list_unions_web_and_runner_sessions():
    user, ws, c = _ctx()
    web = Session.objects.create(workspace=ws, created_by=user, origin=Session.ORIGIN_WEB, title="web")
    # a runner-discovered session: no created_by, but it has a binding
    disc = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="disc")
    runner = Runner.objects.create(name="laptop", workspace=ws, location=Runner.LOCAL,
                                   status=Runner.ONLINE, last_heartbeat_at=timezone.now(), paired_by=user)
    RunnerBinding.objects.create(session=disc, runner=runner, session_key="echo-1",
                                 last_interacted_at=timezone.now())
    body = c.get("/api/chat/").json()
    ids = {row["id"] for row in body}
    assert ids == {str(web.id), str(disc.id)}   # BOTH origins, one row each


def test_list_row_carries_liveness():
    user, ws, c = _ctx()
    disc = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="disc")
    runner = Runner.objects.create(name="jj-air", workspace=ws, location=Runner.LOCAL,
                                   status=Runner.ONLINE, last_heartbeat_at=timezone.now(), paired_by=user)
    RunnerBinding.objects.create(session=disc, runner=runner, session_key="echo-1",
                                 last_interacted_at=timezone.now())
    row = next(r for r in c.get("/api/chat/").json() if r["id"] == str(disc.id))
    assert row["origin"] == "runner"
    assert row["running"] is True                # runner online + fresh interaction
    assert row["runner_name"] == "jj-air"
    assert row["runner_location"] == "local"
    assert row["session_key"] == "echo-1"


def test_idle_when_runner_offline_or_stale():
    user, ws, c = _ctx()
    disc = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="disc")
    # runner never heartbeated -> live_status != ONLINE
    runner = Runner.objects.create(name="laptop", workspace=ws, location=Runner.LOCAL,
                                   status=Runner.DISCONNECTED, paired_by=user)
    RunnerBinding.objects.create(session=disc, runner=runner, session_key="echo-1",
                                 last_interacted_at=timezone.now())
    row = next(r for r in c.get("/api/chat/").json() if r["id"] == str(disc.id))
    assert row["running"] is False
    assert row["runner_name"] == "laptop"        # still shown, just not "running"


def test_web_session_without_binding_is_idle():
    user, ws, c = _ctx()
    web = Session.objects.create(workspace=ws, created_by=user, origin=Session.ORIGIN_WEB, title="web")
    row = next(r for r in c.get("/api/chat/").json() if r["id"] == str(web.id))
    assert row["origin"] == "web"
    assert row["running"] is False
    assert row["runner_name"] is None
    assert row["runner_location"] is None


def test_running_sorts_first():
    user, ws, c = _ctx()
    idle = Session.objects.create(workspace=ws, created_by=user, origin=Session.ORIGIN_WEB, title="idle")
    live = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="live")
    runner = Runner.objects.create(name="laptop", workspace=ws, location=Runner.LOCAL,
                                   status=Runner.ONLINE, last_heartbeat_at=timezone.now(), paired_by=user)
    RunnerBinding.objects.create(session=live, runner=runner, session_key="echo-1",
                                 last_interacted_at=timezone.now())
    body = c.get("/api/chat/").json()
    assert body[0]["id"] == str(live.id)         # running row floats to the top
