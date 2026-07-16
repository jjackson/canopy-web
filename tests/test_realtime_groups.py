"""SP1 Task 2 — group names, the turn membership gate, and null-safe publish."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import AnonymousUser, User

from apps.agents.models import Agent
from apps.harness.models import Turn
from apps.realtime import groups
from apps.workspaces.models import Workspace, WorkspaceMembership


def test_turn_group_is_stable():
    tid = uuid.uuid4()
    assert groups.turn_group(tid) == f"turn.{tid.hex}"
    # accepts a str too, and normalizes to the same group
    assert groups.turn_group(str(tid)) == groups.turn_group(tid)


def test_supervisor_user_group():
    assert groups.supervisor_user_group(7) == "supervisor.user.7"


@pytest.mark.django_db
def test_user_can_read_turn_by_workspace_membership():
    owner = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=owner)
    WorkspaceMembership.objects.create(user=owner, workspace=ws, role=WorkspaceMembership.OWNER)
    agent = Agent.objects.create(slug="echo", name="Echo", workspace=ws, owner=owner)
    turn = Turn.objects.create(agent=agent, origin=Turn.ORIGIN_BOARD, idempotency_key="k1")

    assert groups.user_can_read_turn(owner, turn) is True
    outsider = User.objects.create_user("no", "no@dimagi.com", "pw")
    assert groups.user_can_read_turn(outsider, turn) is False
    assert groups.user_can_read_turn(AnonymousUser(), turn) is False


@pytest.mark.django_db
def test_user_cannot_read_workspaceless_turn():
    # An agent with no workspace has no tenant to gate on -> not readable.
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    agent = Agent.objects.create(slug="loner", name="Loner")
    turn = Turn.objects.create(agent=agent, origin=Turn.ORIGIN_BOARD, idempotency_key="k1")
    assert groups.user_can_read_turn(user, turn) is False


@pytest.mark.django_db
def test_superuser_can_read_any_turn():
    su = User.objects.create_superuser("admin", "admin@dimagi.com", "pw")
    agent = Agent.objects.create(slug="loner", name="Loner")
    turn = Turn.objects.create(agent=agent, origin=Turn.ORIGIN_BOARD, idempotency_key="k1")
    assert groups.user_can_read_turn(su, turn) is True


def test_publish_is_noop_when_no_layer(monkeypatch):
    monkeypatch.setattr(groups, "get_channel_layer", lambda: None)
    groups.publish("turn.x", {"type": "turn.event"})  # must not raise


def test_publish_swallows_layer_errors(monkeypatch):
    def boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(groups, "get_channel_layer", boom)
    groups.publish("turn.x", {"type": "turn.event"})  # must not raise
