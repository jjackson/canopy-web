"""Verifies the non-breaking backfill: a pre-scoping agent (Echo) and the human
who operates it both land in the default workspace, so Echo's live calls keep
working after scoping turns on."""
from __future__ import annotations

import importlib

import pytest
from django.apps import apps as global_apps
from django.contrib.auth import get_user_model

from apps.agents.models import Agent
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db
User = get_user_model()

_backfill = importlib.import_module(
    "apps.agents.migrations.0007_backfill_default_workspace"
).backfill


def test_backfill_scopes_existing_agent_and_members(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = "dimagi.com"
    su = User.objects.create(username="su", email="su@dimagi.com", is_superuser=True)
    jj = User.objects.create(username="jj", email="jj@dimagi.com")  # Echo's PAT human
    echo = Agent.objects.create(slug="echo", name="Echo")  # pre-scoping: no workspace
    assert echo.workspace_id is None

    _backfill(global_apps, None)

    ws = Workspace.objects.get(slug="dimagi")
    echo.refresh_from_db()
    assert echo.workspace_id == ws.slug  # agent scoped
    assert WorkspaceMembership.objects.get(workspace=ws, user=su).role == "owner"
    assert WorkspaceMembership.objects.get(workspace=ws, user=jj).role == "editor"


def test_backfill_noops_without_users():
    _backfill(global_apps, None)
    assert not Workspace.objects.filter(slug="dimagi").exists()
