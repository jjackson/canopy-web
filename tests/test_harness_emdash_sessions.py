"""The emdash session controller — reported sessions + the list the phone reads."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.utils import timezone

from apps.harness.models import EmdashSession, Runner
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


def _user(name):
    return User.objects.create_user(name, f"{name}@dimagi.com", "pw")


def _ws(slug, owner):
    ws = Workspace.objects.create(slug=slug, display_name=slug.title(), created_by=owner)
    WorkspaceMembership.objects.create(user=owner, workspace=ws, role=WorkspaceMembership.OWNER)
    return ws


def _runner(pairer, ws):
    return Runner.objects.create(
        name="jj-mbp", kind=Runner.EMDASH, host="jj-mac", paired_by=pairer, workspace=ws,
        status=Runner.ONLINE, last_heartbeat_at=timezone.now(),
    )


def test_a_runner_cannot_report_the_same_task_twice():
    jj = _user("jj")
    ws = _ws("dimagi", jj)
    runner = _runner(jj, ws)
    EmdashSession.objects.create(runner=runner, workspace=ws, emdash_task="cloud-runner", project="canopy-web")
    with pytest.raises(IntegrityError):
        EmdashSession.objects.create(runner=runner, workspace=ws, emdash_task="cloud-runner", project="canopy-web")


def _report(client, runner_id, sessions):
    return client.post(
        f"/api/harness/runners/{runner_id}/sessions",
        {"sessions": sessions},
        content_type="application/json",
    )


def test_report_is_wholesale_and_upserts_a_sessionlink_for_continue():
    from django.test import Client
    from apps.harness.models import SessionLink

    jj = _user("jj")
    ws = _ws("dimagi", jj)
    runner = _runner(jj, ws)
    c = Client()
    c.force_login(jj)

    r1 = _report(c, runner.id, [
        {"emdash_task": "cloud-runner", "project": "canopy-web", "status": "in_progress",
         "last_interacted_at": "2026-07-16T15:52:00Z"},
        {"emdash_task": "ddd", "project": "canopy-web", "status": "in_progress",
         "last_interacted_at": "2026-07-16T12:41:00Z"},
    ])
    assert r1.status_code == 200, r1.content
    assert EmdashSession.objects.filter(runner=runner).count() == 2
    # The continue substrate: a SessionLink per session, keyed emdash:{task}.
    link = SessionLink.objects.get(project="canopy-web", thread_key="emdash:cloud-runner")
    assert link.live_emdash_task_id == "cloud-runner"
    assert link.live_runner_id == runner.id
    assert link.workspace_id == "dimagi"

    # A re-report with one session gone removes it (wholesale, not merge).
    r2 = _report(c, runner.id, [
        {"emdash_task": "cloud-runner", "project": "canopy-web", "status": "in_progress",
         "last_interacted_at": "2026-07-16T15:59:00Z"},
    ])
    assert r2.status_code == 200
    tasks = set(EmdashSession.objects.filter(runner=runner).values_list("emdash_task", flat=True))
    assert tasks == {"cloud-runner"}


def test_a_non_owner_cannot_report_for_another_users_runner():
    from django.test import Client

    jj = _user("jj")
    ws = _ws("dimagi", jj)
    runner = _runner(jj, ws)
    mallory = _user("mallory")
    _ws("mallory-space", mallory)
    c = Client()
    c.force_login(mallory)

    resp = _report(c, runner.id, [{"emdash_task": "x", "project": "canopy-web"}])
    assert resp.status_code == 404
    assert EmdashSession.objects.filter(runner=runner).count() == 0
