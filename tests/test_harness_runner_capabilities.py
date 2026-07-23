"""PATCH /api/harness/runners/{id} — update a paired runner's capabilities.

The only prior way to add `projects` to a runner was to re-pair, which mints a
new runner and orphans the old one's RunnerBindings. This lets a runner opt into
driving repos in place.
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from apps.harness.models import Runner
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


def _user(name):
    return User.objects.create_user(name, f"{name}@dimagi.com", "pw")


def _ws(slug, owner):
    ws = Workspace.objects.create(slug=slug, display_name=slug.title(), created_by=owner)
    WorkspaceMembership.objects.create(user=owner, workspace=ws, role=WorkspaceMembership.OWNER)
    return ws


def _runner(pairer, ws, **kw):
    return Runner.objects.create(
        name="jj-mbp", kind=Runner.EMDASH, host="jj-mac", paired_by=pairer, workspace=ws,
        status=Runner.ONLINE, last_heartbeat_at=timezone.now(),
        capabilities={"agents": ["echo"]}, **kw,
    )


def _patch(client, runner_id, caps):
    return client.patch(
        f"/api/harness/runners/{runner_id}",
        {"capabilities": caps},
        content_type="application/json",
    )


def test_owner_adds_projects_to_a_paired_runner():
    jj = _user("jj")
    ws = _ws("dimagi", jj)
    runner = _runner(jj, ws)
    c = Client()
    c.force_login(jj)

    resp = _patch(c, runner.id, {"agents": ["echo"], "projects": ["canopy-web"]})

    assert resp.status_code == 200, resp.content
    runner.refresh_from_db()
    assert runner.project_names() == ["canopy-web"]
    assert runner.agent_slugs() == ["echo"]


def test_replacement_is_wholesale():
    """Sending {} clears capabilities — the caller owns the full set, like the
    skill catalog's PUT. No accidental merge that leaves stale entries."""
    jj = _user("jj")
    ws = _ws("dimagi", jj)
    runner = _runner(jj, ws)
    c = Client()
    c.force_login(jj)

    _patch(c, runner.id, {"projects": ["canopy-web"]})
    runner.refresh_from_db()
    assert runner.agent_slugs() == []  # the prior agents entry is gone
    assert runner.project_names() == ["canopy-web"]


def test_a_non_owner_cannot_touch_another_users_runner():
    """404 not 403 — _runner_or_404 must not leak that the runner exists."""
    jj = _user("jj")
    ws = _ws("dimagi", jj)
    runner = _runner(jj, ws)

    mallory = _user("mallory")
    _ws("mallory-space", mallory)
    c = Client()
    c.force_login(mallory)

    resp = _patch(c, runner.id, {"projects": ["canopy-web"]})
    assert resp.status_code == 404
    runner.refresh_from_db()
    assert runner.project_names() == []  # untouched
