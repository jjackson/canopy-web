"""Regressions found by using the converged Sessions UI on prod (2026-07-23).

Three distinct bugs, all rooted in the API not surfacing what the RunnerBinding
already held:
  1. every row rendered `created_at` (when the report sweep first NOTICED the
     session), so a long-dead repo and a live one both read "4h ago";
  2. opening a runner-discovered session showed "Start the conversation" even
     though the binding carried a rolling tail;
  3. sending into one spawned a FRESH emdash session, because the turn's
     thread_key was the canopy Session id while the binding is keyed
     `emdash:<task>`.
"""
import datetime as dt

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from apps.canopy_sessions.models import Message, RunnerBinding, Session
from apps.harness.models import Runner
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


def _ctx():
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="w1", display_name="W1", created_by=user)
    WorkspaceMembership.objects.create(user=user, workspace=ws, role=WorkspaceMembership.OWNER)
    runner = Runner.objects.create(
        name="jj-mbp", workspace=ws, location=Runner.LOCAL, paired_by=user,
        host="jj@mbp", status=Runner.ONLINE, last_heartbeat_at=timezone.now(),
    )
    c = Client(); c.force_login(user)
    return user, ws, runner, c


def _discovered(ws, runner, *, key="ace-demo", tail=None, last=None, thread_key=None, host=None):
    s = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title=key, project="ace")
    RunnerBinding.objects.create(
        session=s, runner=runner, session_key=key,
        thread_key=(f"emdash:{key}" if thread_key is None else thread_key),
        host=(runner.host if host is None else host),
        tail=tail or [], last_interacted_at=last,
    )
    return s


# --- 1. the timestamp bug -------------------------------------------------

def test_last_activity_uses_binding_not_row_creation():
    """created_at is when canopy first NOTICED it — identical across a sweep."""
    _u, ws, runner, c = _ctx()
    recent = timezone.now() - dt.timedelta(minutes=3)
    stale = timezone.now() - dt.timedelta(days=6)
    live = _discovered(ws, runner, key="canopy-web", last=recent)
    dead = _discovered(ws, runner, key="reef", last=stale)

    rows = {r["id"]: r for r in c.get("/api/canopy-sessions/").json()}
    assert rows[str(live.id)]["last_activity_at"][:16] == recent.isoformat()[:16]
    assert rows[str(dead.id)]["last_activity_at"][:16] == stale.isoformat()[:16]
    # the actual symptom: they must NOT report the same age
    assert rows[str(live.id)]["last_activity_at"] != rows[str(dead.id)]["last_activity_at"]


def test_list_sorted_by_real_activity_not_creation():
    _u, ws, runner, c = _ctx()
    old = _discovered(ws, runner, key="old", last=timezone.now() - dt.timedelta(days=2))
    new = _discovered(ws, runner, key="new", last=timezone.now() - dt.timedelta(minutes=1))
    ids = [r["id"] for r in c.get("/api/canopy-sessions/").json()]
    assert ids.index(str(new.id)) < ids.index(str(old.id))
    assert str(old.id) in ids


def test_web_session_falls_back_to_newest_message():
    user, ws, _r, c = _ctx()
    s = Session.objects.create(workspace=ws, created_by=user, origin=Session.ORIGIN_WEB, title="web")
    msg_at = timezone.now() - dt.timedelta(minutes=2)
    m = Message.objects.create(session=s, turn_index=0, role=Message.USER, plaintext="hi")
    Message.objects.filter(pk=m.pk).update(created_at=msg_at)
    row = next(r for r in c.get("/api/canopy-sessions/").json() if r["id"] == str(s.id))
    assert row["last_activity_at"][:16] == msg_at.isoformat()[:16]


# --- 2. the blank-panel bug ----------------------------------------------

def test_discovered_session_renders_its_binding_tail():
    """No Message rows yet — the panel must still open with recent context."""
    _u, ws, runner, c = _ctx()
    tail = [{"role": "user", "text": "q1"}, {"role": "assistant", "text": "a1"}]
    s = _discovered(ws, runner, tail=tail, last=timezone.now())
    body = c.get(f"/api/canopy-sessions/{s.id}").json()
    assert [m["plaintext"] for m in body["messages"]] == ["q1", "a1"]
    # negative indices: order before any real row, never collide with a backfill (0..n)
    assert [m["turn_index"] for m in body["messages"]] == [-2, -1]


def test_real_rows_win_over_the_tail():
    _u, ws, runner, c = _ctx()
    s = _discovered(ws, runner, tail=[{"role": "assistant", "text": "stale tail"}])
    Message.objects.create(session=s, turn_index=0, role=Message.USER, plaintext="real")
    body = c.get(f"/api/canopy-sessions/{s.id}").json()
    assert [m["plaintext"] for m in body["messages"]] == ["real"]


# --- 3. the "spawned a new session" bug ----------------------------------

def test_send_reuses_the_bindings_thread_key():
    """Sending str(session.id) matched no binding -> runner spawned a fresh session."""
    from apps.canopy_sessions import services
    user, ws, runner, _c = _ctx()
    s = _discovered(ws, runner, key="ace-demo")
    _msg, turn = services.send_message(session=s, user=user, text="hello", client_id="c1")
    assert turn.origin_ref["thread_key"] == "emdash:ace-demo"     # the LIVE session
    assert turn.origin_ref["chat_session_id"] == str(s.id)        # bridge target unchanged


def test_web_session_send_still_keys_on_the_session_id():
    from apps.canopy_sessions import services
    user, ws, _r, _c = _ctx()
    s = Session.objects.create(workspace=ws, created_by=user, origin=Session.ORIGIN_WEB, title="web")
    _msg, turn = services.send_message(session=s, user=user, text="hello", client_id="c1")
    assert turn.origin_ref["thread_key"] == str(s.id)


# --- report path heals a legacy binding without stealing one --------------

def test_report_fills_empty_identity_but_never_overwrites():
    from types import SimpleNamespace
    from apps.harness.services import replace_reported_sessions
    _u, ws, runner, _c = _ctx()
    legacy = _discovered(ws, runner, key="legacy", thread_key="", host="")   # pre-fold row
    owned = _discovered(ws, runner, key="owned", thread_key="phone:jj:echo")

    rep = lambda k: SimpleNamespace(emdash_task=k, project="ace", status="running",
                                    last_interacted_at=None, recent_messages=[])
    replace_reported_sessions(runner, ws, [rep("legacy"), rep("owned")])

    healed = RunnerBinding.objects.get(session=legacy)
    assert healed.thread_key == "emdash:legacy" and healed.host == runner.host  # filled
    assert healed.reusable_by(runner) is True                                   # now reusable
    assert RunnerBinding.objects.get(session=owned).thread_key == "phone:jj:echo"  # NOT stolen
