"""POST /api/harness/turns/ for repo targets."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.agents.models import Agent
from apps.harness.models import Turn
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db

URL = "/api/harness/turns/"


def _user(name):
    return get_user_model().objects.create_user(username=name, email=f"{name}@dimagi.com")


def _ws(slug, owner):
    ws = Workspace.objects.create(slug=slug, display_name=slug.title(), created_by=owner)
    WorkspaceMembership.objects.create(workspace=ws, user=owner, role=WorkspaceMembership.OWNER)
    return ws


@pytest.fixture
def jj(db):
    return _user("jj")


@pytest.fixture
def canopy(db, jj):
    return _ws("canopy", jj)


@pytest.fixture
def cli(client, jj, canopy):
    client.force_login(jj)
    return client


def _post(cli, **kw):
    body = {"origin": "manual", "idempotency_key": "k1", **kw}
    return cli.post(URL, data=body, content_type="application/json")


def test_enqueue_a_project_turn(cli, canopy):
    resp = _post(cli, project="canopy-web", prompt="fix the header")
    assert resp.status_code == 201, resp.content

    turn = Turn.objects.get(idempotency_key="k1")
    assert turn.agent_id is None
    assert turn.project == "canopy-web"
    assert turn.workspace_id == canopy.slug
    assert resp.json()["target"] == "canopy-web"


def test_a_turn_targeting_both_is_rejected(cli, canopy):
    Agent.objects.create(slug="echo", name="Echo", workspace=canopy)
    resp = _post(cli, project="canopy-web", agent_slug="echo")
    assert resp.status_code == 422


def test_a_turn_targeting_nothing_is_rejected(cli, canopy):
    assert _post(cli).status_code == 422


def test_a_project_enqueue_by_a_user_with_no_workspace_404s(client, db):
    """Fail closed and do not leak: a caller with no unambiguous tenant has
    nowhere to put the turn. 404, not 403 — the harness must not disclose which
    tenants exist (the rule _agent_or_404 already follows)."""
    loner = _user("loner")
    client.force_login(loner)
    resp = _post(client, project="canopy-web")
    assert resp.status_code == 404
    assert not Turn.objects.exists()


def test_idempotency_collapses_duplicate_project_turns(cli, canopy):
    first = _post(cli, project="canopy-web")
    second = _post(cli, project="canopy-web")

    assert first.status_code == 201
    assert second.status_code == 200  # replay, not a second turn
    assert Turn.objects.filter(project="canopy-web").count() == 1


def test_agent_turns_still_enqueue(cli, canopy):
    Agent.objects.create(slug="echo", name="Echo", workspace=canopy)
    resp = _post(cli, agent_slug="echo", prompt="/echo:story-ideation")

    assert resp.status_code == 201, resp.content
    turn = Turn.objects.get(idempotency_key="k1")
    assert turn.project == ""
    # Agent turns DERIVE tenancy via agent.workspace — they must not denormalize
    # a second copy that can drift out of step with the agent's own workspace.
    assert turn.workspace_id is None


def test_a_multi_workspace_user_is_told_to_name_one_not_404d(client, db, jj, canopy):
    """The gap my suite had, found only by probing prod.

    Every test user here had exactly ONE workspace, so current_workspace always
    resolved. The real prod user belongs to two ('connect' and 'dimagi'), which
    makes the default ambiguous — and the flat route 404'd every project enqueue
    while reporting "workspace not found". The turn was fine; the error was a lie.

    Nothing to protect here: they are the caller's own workspaces, so name the fix
    rather than hide behind the 404-not-403 rule (which exists to avoid leaking
    OTHER tenants' existence).
    """
    _ws("dimagi", jj)  # jj is now in two
    client.force_login(jj)

    resp = _post(client, project="canopy-web")

    assert resp.status_code == 422, resp.content
    assert "multiple workspaces" in resp.json()["detail"]
    assert not Turn.objects.exists()


def test_a_multi_workspace_user_can_enqueue_via_the_tenant_scoped_route(client, db, jj, canopy):
    """The other half: naming the workspace works. Verified against prod too —
    POST /api/w/connect/harness/turns/ queued a canopy-web turn."""
    _ws("dimagi", jj)
    client.force_login(jj)

    resp = client.post(
        "/api/w/canopy/harness/turns/",
        data={"project": "canopy-web", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    )

    assert resp.status_code == 201, resp.content
    assert Turn.objects.get(idempotency_key="k1").workspace_id == "canopy"
