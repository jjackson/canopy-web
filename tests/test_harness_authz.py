"""Authorization tests for /api/harness — a non-member must get 404, never 403,
and never a leak that the resource exists. Mirrors apps/agents' posture."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.agents.models import Agent
from apps.harness.models import Runner, Turn
from apps.workspaces import services as wsvc
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


@pytest.fixture()
def owner():
    return User.objects.create_user("owner", "owner@dimagi.com", "pw")


@pytest.fixture()
def workspace(owner):
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=owner)
    WorkspaceMembership.objects.create(user=owner, workspace=ws, role=WorkspaceMembership.OWNER)
    return ws


@pytest.fixture()
def stranger():
    """Authenticated, but a member of nothing. auto_join_workspaces keys off the
    email domain, so use one outside the auto-join set."""
    return User.objects.create_user("stranger", "stranger@example.org", "pw")


@pytest.fixture()
def agent(workspace):
    return Agent.objects.create(slug="echo", name="Echo", workspace=workspace)


@pytest.fixture()
def owner_client(owner):
    c = Client()
    c.force_login(owner)
    return c


@pytest.fixture()
def stranger_client(stranger):
    c = Client()
    c.force_login(stranger)
    return c


def _enqueue(client, slug="echo", key="k1"):
    return client.post(
        "/api/harness/turns/",
        {"agent_slug": slug, "origin": "manual", "idempotency_key": key, "prompt": "/echo:turn"},
        content_type="application/json",
    )


def test_member_can_enqueue(owner_client, agent):
    assert _enqueue(owner_client).status_code == 201


def test_stranger_enqueueing_for_someone_elses_agent_gets_404(stranger_client, agent):
    """404, not 403: a non-member must not learn the agent exists."""
    resp = _enqueue(stranger_client)
    assert resp.status_code == 404


def test_stranger_cannot_read_someone_elses_turn(owner_client, stranger_client, agent):
    turn_id = _enqueue(owner_client).json()["id"]
    assert stranger_client.get(f"/api/harness/turns/{turn_id}").status_code == 404


def test_stranger_cannot_finish_someone_elses_turn(owner_client, stranger_client, agent):
    turn_id = _enqueue(owner_client).json()["id"]
    resp = stranger_client.post(
        f"/api/harness/turns/{turn_id}/finish",
        {"status": "done", "result_note": "pwned"},
        content_type="application/json",
    )
    assert resp.status_code == 404
    assert Turn.objects.get(pk=turn_id).status == Turn.QUEUED  # untouched


def test_stranger_cannot_heartbeat_someone_elses_runner(owner_client, stranger_client, workspace):
    rid = owner_client.post(
        "/api/harness/runners/",
        {"name": "jj-mbp", "kind": "emdash", "capabilities": {"agents": ["echo"]}},
        content_type="application/json",
    ).json()["id"]
    resp = stranger_client.post(
        f"/api/harness/runners/{rid}/heartbeat",
        {"active_turn_ids": [], "degraded": False, "note": ""},
        content_type="application/json",
    )
    assert resp.status_code == 404


def test_stranger_cannot_claim_as_someone_elses_runner(owner_client, stranger_client, agent):
    rid = owner_client.post(
        "/api/harness/runners/",
        {"name": "jj-mbp", "kind": "emdash", "capabilities": {"agents": ["echo"]}},
        content_type="application/json",
    ).json()["id"]
    _enqueue(owner_client)
    assert stranger_client.post(f"/api/harness/runners/{rid}/claim").status_code == 404


def test_list_turns_only_shows_my_tenants_turns(owner_client, stranger_client, agent):
    _enqueue(owner_client)
    resp = stranger_client.get("/api/harness/turns/")
    assert resp.status_code == 200
    assert resp.json() == []  # filtered, not 404 — a list of nothing


def test_null_workspace_agent_stays_ungated(owner_client):
    """Agents predating tenancy have workspace=None. They must keep working —
    the existing suite creates agents exactly this way."""
    Agent.objects.create(slug="legacy", name="Legacy")
    assert _enqueue(owner_client, slug="legacy", key="k-legacy").status_code == 201


# --- pair_runner workspace-assignment branches (Task 2, uncovered) ---------


def test_pair_runner_with_explicit_workspace_the_caller_is_member_of(owner_client, workspace):
    resp = owner_client.post(
        "/api/harness/runners/",
        {"name": "jj-mbp", "kind": "emdash", "capabilities": {}, "workspace": workspace.slug},
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert resp.json()["workspace"] == workspace.slug


def test_pair_runner_with_explicit_workspace_the_caller_is_not_member_of_gets_404(
    stranger_client, workspace
):
    """404, not 403 — same as a nonexistent workspace, no existence leak."""
    resp = stranger_client.post(
        "/api/harness/runners/",
        {"name": "jj-mbp", "kind": "emdash", "capabilities": {}, "workspace": workspace.slug},
        content_type="application/json",
    )
    assert resp.status_code == 404
    assert not Runner.objects.filter(name="jj-mbp").exists()


def test_pair_runner_with_no_workspace_homes_to_the_callers_sole_membership(owner_client, owner, workspace):
    """No `workspace` key + exactly one membership -> homed to that default workspace.
    `wsvc.user_default_workspace` only resolves when the caller has EXACTLY one
    membership, so `owner`'s single `workspace` membership makes this unambiguous."""
    assert wsvc.user_default_workspace(owner).slug == workspace.slug  # sanity: exactly one
    resp = owner_client.post(
        "/api/harness/runners/",
        {"name": "jj-mbp", "kind": "emdash", "capabilities": {}},
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert resp.json()["workspace"] == workspace.slug
