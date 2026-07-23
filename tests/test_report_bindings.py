"""The report path upserts a durable Session(origin=runner) + RunnerBinding
per reported emdash session, keyed by (runner, session_key) — replacing the
deleted EmdashSession model."""
from __future__ import annotations

import pytest
from types import SimpleNamespace

from django.contrib.auth import get_user_model

from apps.harness.services import replace_reported_sessions
from apps.harness.models import Runner
from apps.canopy_sessions.models import Session, RunnerBinding
from apps.workspaces.models import Workspace

pytestmark = pytest.mark.django_db


def _reported(task, msgs):
    return SimpleNamespace(
        emdash_task=task, project="canopy-web", status="running",
        last_interacted_at=None, recent_messages=msgs,
    )


def _user():
    return get_user_model().objects.create(username="jj", email="jj@dimagi.com")


def test_report_creates_session_and_binding():
    jj = _user()
    ws = Workspace.objects.create(slug="w1", display_name="W1", created_by=jj)
    runner = Runner.objects.create(name="laptop", workspace=ws, location=Runner.LOCAL)
    n = replace_reported_sessions(runner, ws, [_reported("feat-x", [{"role": "assistant", "text": "hi"}])])
    assert n == 1
    b = RunnerBinding.objects.get(runner=runner, session_key="feat-x")
    assert b.session.origin == Session.ORIGIN_RUNNER
    assert b.tail == [{"role": "assistant", "text": "hi"}]


def test_report_is_idempotent_and_updates_tail():
    jj = _user()
    ws = Workspace.objects.create(slug="w1", display_name="W1", created_by=jj)
    runner = Runner.objects.create(name="laptop", workspace=ws, location=Runner.LOCAL)
    replace_reported_sessions(runner, ws, [_reported("feat-x", [{"role": "user", "text": "a"}])])
    replace_reported_sessions(runner, ws, [_reported("feat-x", [{"role": "assistant", "text": "b"}])])
    assert Session.objects.filter(runner_binding__session_key="feat-x").count() == 1
    b = RunnerBinding.objects.get(runner=runner, session_key="feat-x")
    assert b.tail == [{"role": "assistant", "text": "b"}]


def test_dropped_session_clears_live_but_keeps_session():
    jj = _user()
    ws = Workspace.objects.create(slug="w1", display_name="W1", created_by=jj)
    runner = Runner.objects.create(name="laptop", workspace=ws, location=Runner.LOCAL)
    replace_reported_sessions(runner, ws, [_reported("feat-x", [])])
    replace_reported_sessions(runner, ws, [])  # feat-x no longer open
    b = RunnerBinding.objects.get(session_key="feat-x")
    assert b.runner_id is None       # live pointer cleared
    assert Session.objects.filter(runner_binding=b).exists()  # session kept


def test_list_visible_sessions_maps_to_wire_shape():
    from django.utils import timezone

    from apps.harness.services import list_visible_sessions
    from apps.workspaces.services import ensure_member
    from apps.workspaces.models import WorkspaceMembership

    jj = _user()
    ws = Workspace.objects.create(slug="w1", display_name="W1", created_by=jj)
    ensure_member(ws, jj, WorkspaceMembership.OWNER)
    runner = Runner.objects.create(
        name="laptop", workspace=ws, location=Runner.LOCAL,
        status=Runner.ONLINE, paired_by=jj, last_heartbeat_at=timezone.now(),
    )
    replace_reported_sessions(runner, ws, [_reported("feat-x", [{"role": "assistant", "text": "hi"}])])
    rows = list_visible_sessions(jj)
    assert len(rows) == 1
    r = rows[0]
    assert r.emdash_task == "feat-x"
    assert r.recent_messages == [{"role": "assistant", "text": "hi"}]
    assert r.runner_name == "laptop"
