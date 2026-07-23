import uuid
import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.canopy_sessions.models import RunnerBinding, Session
from apps.harness.models import Runner
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


def _ctx():
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="w1", display_name="W1", created_by=user)
    WorkspaceMembership.objects.create(user=user, workspace=ws, role=WorkspaceMembership.OWNER)
    runner = Runner.objects.create(name="laptop", workspace=ws, location=Runner.LOCAL,
                                   status=Runner.ONLINE, paired_by=user)
    c = Client(); c.force_login(user)
    return user, ws, runner, c


def test_streams_lists_only_desired_bindings():
    user, ws, runner, c = _ctx()
    s1 = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, project="echo", title="a")
    s2 = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="b")
    RunnerBinding.objects.create(session=s1, runner=runner, session_key="echo-1",
                                 stream_desired=True)
    RunnerBinding.objects.create(session=s2, runner=runner, session_key="echo-2",
                                 stream_desired=False)  # not attached -> excluded
    body = c.get(f"/api/harness/runners/{runner.id}/streams").json()
    assert [x["session_key"] for x in body["streams"]] == ["echo-1"]
    assert body["streams"][0]["session_id"] == str(s1.id)
    assert body["streams"][0]["project"] == "echo"


def test_session_stream_publishes_stream_frames(monkeypatch):
    user, ws, runner, c = _ctx()
    s = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="a")
    RunnerBinding.objects.create(session=s, runner=runner, session_key="echo-1", stream_desired=True)
    published = []
    monkeypatch.setattr("apps.realtime.groups.publish", lambda g, m: published.append((g, m)))
    body = c.post(
        f"/api/harness/runners/{runner.id}/session-stream",
        data={"session_id": str(s.id),
              "events": [{"kind": "assistant", "seq": 0, "payload": {"text": "hi"}}]},
        content_type="application/json",
    ).json()
    assert body == {"count": 1}
    assert len(published) == 1
    group, frame = published[0]
    assert group.endswith(s.id.hex)                 # the session group
    assert frame["type"] == "chat.turn_event"
    assert frame["turn_id"] is None                 # turn-less live frame
    assert frame["event"] == {"kind": "assistant", "seq": 0, "payload": {"text": "hi"}}


def test_session_stream_rejects_unbound_runner():
    user, ws, runner, c = _ctx()
    s = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="a")
    # binding belongs to a DIFFERENT runner
    other = Runner.objects.create(name="other", workspace=ws, location=Runner.LOCAL, paired_by=user)
    RunnerBinding.objects.create(session=s, runner=other, session_key="echo-1")
    resp = c.post(
        f"/api/harness/runners/{runner.id}/session-stream",
        data={"session_id": str(s.id), "events": []},
        content_type="application/json",
    )
    assert resp.status_code == 404
