"""The emdash session controller — reported sessions + the list the phone reads."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.chat.models import RunnerBinding, Session
from apps.harness.models import Runner
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
    assert RunnerBinding.objects.filter(runner=runner).count() == 2
    binding = RunnerBinding.objects.get(runner=runner, session_key="cloud-runner")
    assert binding.session.origin == Session.ORIGIN_RUNNER
    # The continue substrate: a SessionLink per session, keyed emdash:{task}.
    link = SessionLink.objects.get(project="canopy-web", thread_key="emdash:cloud-runner")
    assert link.live_emdash_task_id == "cloud-runner"
    assert link.live_runner_id == runner.id
    assert link.workspace_id == "dimagi"

    # A re-report with one session gone clears its live binding (durable, not deleted).
    r2 = _report(c, runner.id, [
        {"emdash_task": "cloud-runner", "project": "canopy-web", "status": "in_progress",
         "last_interacted_at": "2026-07-16T15:59:00Z"},
    ])
    assert r2.status_code == 200
    live_tasks = set(
        RunnerBinding.objects.filter(runner=runner).values_list("session_key", flat=True)
    )
    assert live_tasks == {"cloud-runner"}
    dropped = RunnerBinding.objects.get(session_key="ddd")
    assert dropped.runner_id is None  # live pointer cleared, session kept
    assert Session.objects.filter(runner_binding=dropped).exists()


def test_report_dedupes_duplicate_task_names_keeping_newest():
    """emdash task names are NOT unique — a report can carry two open sessions that
    share a name. The report must dedupe, keeping the newest (the runner sends
    newest-first, so the first occurrence wins) — regression: two "mobile" tasks
    stranded the whole list, 2026-07-20."""
    from django.test import Client

    jj = _user("jj")
    ws = _ws("dimagi", jj)
    runner = _runner(jj, ws)
    c = Client()
    c.force_login(jj)

    resp = _report(c, runner.id, [
        {"emdash_task": "mobile", "project": "canopy-web", "status": "in_progress",
         "last_interacted_at": "2026-07-20T20:20:00Z"},
        {"emdash_task": "mobile", "project": "canopy-web", "status": "done",
         "last_interacted_at": "2026-07-17T15:48:00Z"},
    ])
    assert resp.status_code == 200, resp.content
    rows = RunnerBinding.objects.filter(runner=runner)
    assert rows.count() == 1
    kept = rows.get()
    assert kept.session_key == "mobile"
    assert kept.status == "in_progress"  # the newer (first) namesake won


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
    assert RunnerBinding.objects.filter(runner=runner).count() == 0


@pytest.mark.skip(reason="list_visible_sessions rewritten in unified-sessions Plan 1 Task 5")
def test_list_is_tenant_scoped_and_hides_offline_runners():
    from datetime import timedelta
    from django.test import Client

    jj = _user("jj")
    ws = _ws("dimagi", jj)
    live = _runner(jj, ws)
    EmdashSession.objects.create(runner=live, workspace=ws, emdash_task="cloud-runner",
                                 project="canopy-web", status="in_progress")

    # An offline runner's session is hidden (not deleted).
    stale = Runner.objects.create(
        name="old-mbp", kind=Runner.EMDASH, host="old", paired_by=jj, workspace=ws,
        status=Runner.ONLINE, last_heartbeat_at=timezone.now() - timedelta(hours=2),
    )
    EmdashSession.objects.create(runner=stale, workspace=ws, emdash_task="ghost", project="canopy-web")

    c = Client()
    c.force_login(jj)
    rows = c.get("/api/harness/sessions").json()
    tasks = {r["emdash_task"] for r in rows}
    assert tasks == {"cloud-runner"}  # ghost hidden: its runner is not live

    # A non-member sees nothing.
    mallory = _user("mallory")
    _ws("mallory-space", mallory)
    mc = Client()
    mc.force_login(mallory)
    assert mc.get("/api/harness/sessions").json() == []


@pytest.mark.skip(reason="list_visible_sessions rewritten in unified-sessions Plan 1 Task 5")
def test_list_auto_joins_a_domain_matching_user_with_no_membership_row():
    """A @dimagi.com user who has never hit any other endpoint has NO explicit
    WorkspaceMembership row yet. The flat GET /api/harness/sessions path is
    never touched by WorkspaceResolveMiddleware's tenant-prefix auto-join (that
    only fires for /api/w/{ws}/... paths), so list_visible_sessions must call
    wsvc.auto_join_workspaces itself — mirroring list_turns — or a fresh
    domain-matching teammate gets an empty list instead of their workspace's
    sessions."""
    from django.test import Client

    owner = _user("owner")
    ws = _ws("dimagi", owner)
    ws.auto_join_domains = ["dimagi.com"]
    ws.save(update_fields=["auto_join_domains"])
    runner = _runner(owner, ws)
    EmdashSession.objects.create(runner=runner, workspace=ws, emdash_task="cloud-runner",
                                 project="canopy-web", status="in_progress")

    newcomer = _user("newcomer")  # newcomer@dimagi.com, no WorkspaceMembership row
    assert not WorkspaceMembership.objects.filter(user=newcomer).exists()

    c = Client()
    c.force_login(newcomer)
    rows = c.get("/api/harness/sessions").json()
    tasks = {r["emdash_task"] for r in rows}
    assert tasks == {"cloud-runner"}


@pytest.mark.skip(reason="list_visible_sessions rewritten in unified-sessions Plan 1 Task 5")
def test_list_is_newest_first_by_last_interacted_at():
    from datetime import timedelta
    from django.test import Client

    jj = _user("jj")
    ws = _ws("dimagi", jj)
    runner = _runner(jj, ws)
    EmdashSession.objects.create(
        runner=runner, workspace=ws, emdash_task="older", project="canopy-web",
        status="in_progress", last_interacted_at=timezone.now() - timedelta(hours=1),
    )
    EmdashSession.objects.create(
        runner=runner, workspace=ws, emdash_task="newer", project="canopy-web",
        status="in_progress", last_interacted_at=timezone.now(),
    )

    c = Client()
    c.force_login(jj)
    rows = c.get("/api/harness/sessions").json()
    tasks = [r["emdash_task"] for r in rows]
    assert tasks == ["newer", "older"]
