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
