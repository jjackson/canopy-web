"""Contract tests for the v2 projects + insights Ninja surface.

These tests verify:
- Auth: 401 for anonymous, 200 for force_login sessions.
- Status codes: 200 list, 201 create, 204 delete, 404 not-found, 409 conflict.
- Round-trip: response bodies validate through the corresponding Pydantic schema.
- Bearer xfail: endpoints in the /api/v2/ namespace that depend on middleware
  allowlist keys anchored to /api/projects/ are marked xfail until Phase 5.4.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.projects.models import Project, ProjectAction, ProjectContext
from apps.projects.schemas import (
    InsightOut,
    ProjectDetailOut,
    ProjectListOut,
    ProjectSlugOut,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(username="alice", email="alice@dimagi.com"):
    return User.objects.create_user(username=username, email=email, password="pw")


def _make_project(slug="canopy-web", name="canopy-web", status="active"):
    return Project.objects.create(
        name=name,
        slug=slug,
        repo_url="",
        deploy_url="",
        visibility="public",
        status=status,
        skills=[],
    )


def _auth_client(user=None):
    """Return a logged-in test client."""
    c = Client()
    if user is None:
        user = _make_user()
    c.force_login(user)
    return c


def _post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type="application/json")


def _patch_json(client, url, data):
    return client.patch(url, data=json.dumps(data), content_type="application/json")


def _delete(client, url):
    return client.delete(url)


# ---------------------------------------------------------------------------
# list_projects
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_projects_200_happy_path():
    _make_project()
    c = _auth_client()
    resp = c.get("/api/v2/projects/")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] >= 1
    # Round-trip the first item through ProjectListOut
    ProjectListOut.model_validate(body["items"][0])


@pytest.mark.django_db
def test_list_projects_401_anonymous():
    c = Client()
    resp = c.get("/api/v2/projects/")
    assert resp.status_code == 401
    body = resp.json()
    assert body["status"] == 401


@pytest.mark.django_db
def test_list_projects_pagination():
    user = _make_user()
    for i in range(5):
        _make_project(slug=f"proj-{i}", name=f"Project {i}")
    c = _auth_client(user)
    resp = c.get("/api/v2/projects/?offset=0&limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) <= 2
    assert body["limit"] == 2


# ---------------------------------------------------------------------------
# get_project_slugs
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_project_slugs_200_happy_path():
    _make_project(slug="my-slug", status="active")
    c = _auth_client()
    resp = c.get("/api/v2/projects/slugs/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    slugs = [item["slug"] for item in body]
    assert "my-slug" in slugs
    # Round-trip through schema
    ProjectSlugOut.model_validate(body[0])


@pytest.mark.django_db
@pytest.mark.xfail(
    reason="Bearer bypass updates in Phase 5.4 — middleware allowlist keys on /api/projects/ not /api/v2/projects/"
)
def test_get_project_slugs_bearer_readable():
    """Anonymous Bearer token request to /api/v2/projects/slugs/ should return 200.

    The middleware allowlist keys on /api/projects/slugs/, not /api/v2/projects/slugs/,
    so it never sets _workbench_token_auth=True for this path. The result is a 401.
    Xfail until Phase 5.4 updates the middleware.
    """
    _make_project()
    anon_client = Client()
    # Simulate a bearer-token caller hitting the v2 endpoint directly
    resp = anon_client.get(
        "/api/v2/projects/slugs/",
        HTTP_AUTHORIZATION="Bearer some-workbench-token",
    )
    # Middleware doesn't set _workbench_token_auth for /api/v2/ paths → 401 today
    assert resp.status_code == 200  # expected when Phase 5.4 lands


# ---------------------------------------------------------------------------
# create_project
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_project_201():
    c = _auth_client()
    resp = _post_json(c, "/api/v2/projects/", {
        "name": "New Project",
        "slug": "new-project",
        "visibility": "public",
        "status": "active",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "new-project"
    # Round-trip through schema
    ProjectDetailOut.model_validate(body)


@pytest.mark.django_db
def test_create_project_409_duplicate_slug():
    _make_project(slug="existing")
    c = _auth_client()
    resp = _post_json(c, "/api/v2/projects/", {
        "name": "Dupe",
        "slug": "existing",
        "visibility": "public",
        "status": "active",
    })
    assert resp.status_code == 409
    body = resp.json()
    assert body["status"] == 409
    assert "conflict" in body["type"]


# ---------------------------------------------------------------------------
# get_project (detail)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_project_200():
    _make_project(slug="detail-slug")
    c = _auth_client()
    resp = c.get("/api/v2/projects/detail-slug/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "detail-slug"
    ProjectDetailOut.model_validate(body)


@pytest.mark.django_db
def test_get_project_404_problem_json():
    c = _auth_client()
    resp = c.get("/api/v2/projects/does-not-exist/")
    assert resp.status_code == 404
    body = resp.json()
    assert body["status"] == 404
    assert "not-found" in body["type"]


# ---------------------------------------------------------------------------
# patch_project
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_patch_project_200():
    _make_project(slug="patchme")
    c = _auth_client()
    resp = _patch_json(c, "/api/v2/projects/patchme/", {"status": "archived"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "archived"


# ---------------------------------------------------------------------------
# delete_project
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_project_204():
    _make_project(slug="deleteme")
    c = _auth_client()
    resp = _delete(c, "/api/v2/projects/deleteme/")
    assert resp.status_code == 204
    assert not Project.objects.filter(slug="deleteme").exists()


@pytest.mark.django_db
def test_delete_project_404():
    c = _auth_client()
    resp = _delete(c, "/api/v2/projects/no-such-project/")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# context endpoints
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_context_200():
    p = _make_project(slug="ctx-proj")
    ProjectContext.objects.create(
        project=p, context_type="current_work", content="Working on X", source="test"
    )
    c = _auth_client()
    resp = c.get("/api/v2/projects/ctx-proj/context/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["context_type"] == "current_work"


@pytest.mark.django_db
def test_create_context_201():
    _make_project(slug="ctx-create")
    c = _auth_client()
    resp = _post_json(c, "/api/v2/projects/ctx-create/context/", {
        "context_type": "note",
        "content": "Some note content",
        "source": "test-suite",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["context_type"] == "note"
    assert body["content"] == "Some note content"


@pytest.mark.django_db
@pytest.mark.xfail(
    reason="Bearer bypass updates in Phase 5.4 — middleware allowlist keys on /api/projects/ not /api/v2/projects/"
)
def test_create_context_bearer_writable():
    """Anonymous Bearer token request to /api/v2/projects/{slug}/context/ should return 201.

    Middleware allowlist keys on /api/projects/*/context/, not the v2 path.
    Xfail until Phase 5.4.
    """
    _make_project(slug="bearer-ctx-test")
    anon_client = Client()
    resp = _post_json(
        anon_client,
        "/api/v2/projects/bearer-ctx-test/context/",
        {"context_type": "note", "content": "Bearer note", "source": "machine-caller"},
    )
    # 201 when middleware allows v2 paths; today it returns 401
    assert resp.status_code == 201  # expected when Phase 5.4 lands


@pytest.mark.django_db
def test_get_context_latest_200():
    p = _make_project(slug="ctx-latest")
    ProjectContext.objects.create(
        project=p, context_type="summary", content="Summary text", source="test"
    )
    c = _auth_client()
    resp = c.get("/api/v2/projects/ctx-latest/context/latest/")
    assert resp.status_code == 200
    body = resp.json()
    assert "contexts" in body
    assert "summary" in body["contexts"]


# ---------------------------------------------------------------------------
# actions endpoints
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_actions_200():
    p = _make_project(slug="act-proj")
    ProjectAction.objects.create(
        project=p,
        skill_name="session-review",
        status="completed",
        started_at=dt.datetime(2026, 5, 1, tzinfo=dt.timezone.utc),
    )
    c = _auth_client()
    resp = c.get("/api/v2/projects/act-proj/actions/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["skill_name"] == "session-review"


@pytest.mark.django_db
def test_list_actions_skill_filter():
    p = _make_project(slug="act-filter")
    ProjectAction.objects.create(
        project=p,
        skill_name="session-review",
        status="completed",
        started_at=dt.datetime(2026, 5, 1, tzinfo=dt.timezone.utc),
    )
    ProjectAction.objects.create(
        project=p,
        skill_name="qa",
        status="started",
        started_at=dt.datetime(2026, 5, 2, tzinfo=dt.timezone.utc),
    )
    c = _auth_client()
    resp = c.get("/api/v2/projects/act-filter/actions/?skill=qa")
    assert resp.status_code == 200
    body = resp.json()
    assert all(a["skill_name"] == "qa" for a in body)


@pytest.mark.django_db
def test_create_action_201():
    _make_project(slug="act-create")
    c = _auth_client()
    resp = _post_json(c, "/api/v2/projects/act-create/actions/", {
        "skill_name": "session-review",
        "status": "started",
        "started_at": "2026-05-26T10:00:00Z",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["skill_name"] == "session-review"


@pytest.mark.django_db
@pytest.mark.xfail(
    reason="Bearer bypass updates in Phase 5.4 — middleware allowlist keys on /api/projects/ not /api/v2/projects/"
)
def test_create_action_bearer_writable():
    """POST /actions/ should accept Bearer token — xfail until Phase 5.4."""
    from django.contrib.auth.models import AnonymousUser
    from django.test import RequestFactory

    from apps.api.auth import session_auth

    rf = RequestFactory()
    request = rf.post("/api/v2/projects/x/actions/")
    request.user = AnonymousUser()
    # Without middleware setting _workbench_token_auth, this would fail for v2
    result = session_auth.authenticate(request, None)
    assert result is not None


@pytest.mark.django_db
def test_get_actions_summary_200():
    p = _make_project(slug="act-summary")
    ProjectAction.objects.create(
        project=p,
        skill_name="session-review",
        status="completed",
        started_at=dt.datetime(2026, 5, 1, tzinfo=dt.timezone.utc),
    )
    ProjectAction.objects.create(
        project=p,
        skill_name="session-review",
        status="started",
        started_at=dt.datetime(2026, 5, 2, tzinfo=dt.timezone.utc),
    )
    c = _auth_client()
    resp = c.get("/api/v2/projects/act-summary/actions/summary/")
    assert resp.status_code == 200
    body = resp.json()
    # Should deduplicate — only one entry per skill_name (most recent)
    skill_names = [item["skill_name"] for item in body]
    assert skill_names.count("session-review") == 1


# ---------------------------------------------------------------------------
# batch-context
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_batch_context_201():
    _make_project(slug="batch-ctx")
    c = _auth_client()
    resp = _post_json(c, "/api/v2/projects/batch-context/", {
        "updates": {
            "batch-ctx": [
                {"context_type": "current_work", "content": "Batch work", "source": "test"}
            ]
        }
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["batch-ctx"] == 1


@pytest.mark.django_db
@pytest.mark.xfail(
    reason="Bearer bypass updates in Phase 5.4 — middleware allowlist keys on /api/projects/ not /api/v2/projects/"
)
def test_batch_context_bearer_writable():
    """POST /batch-context/ should accept Bearer tokens — xfail until Phase 5.4.

    The middleware allowlist currently gates on /api/projects/batch-context/,
    not /api/v2/projects/batch-context/, so anonymous Bearer callers get 401.
    """
    _make_project(slug="bearer-test")
    anon_client = Client()
    resp = _post_json(anon_client, "/api/v2/projects/batch-context/", {
        "updates": {
            "bearer-test": [
                {"context_type": "current_work", "content": "Bearer test", "source": "test"}
            ]
        }
    })
    # Should be 201 when Bearer bypass works — currently 401
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_insights_200_happy_path():
    p = _make_project(slug="ins-proj")
    ProjectContext.objects.create(
        project=p, context_type="insight", content="[ship_gap] Open PR", source="canopy:portfolio-review"
    )
    c = _auth_client()
    resp = c.get("/api/v2/insights/")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] >= 1
    InsightOut.model_validate(body["items"][0])


@pytest.mark.django_db
def test_list_insights_401_anonymous():
    c = Client()
    resp = c.get("/api/v2/insights/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_list_insights_category_filter():
    p = _make_project(slug="ins-filter")
    ProjectContext.objects.create(
        project=p, context_type="insight", content="[ship_gap] X", source="test"
    )
    ProjectContext.objects.create(
        project=p, context_type="insight", content="[debt] Y", source="test"
    )
    c = _auth_client()
    resp = c.get("/api/v2/insights/?category=ship_gap")
    assert resp.status_code == 200
    body = resp.json()
    for item in body["items"]:
        assert item["content"].startswith("[ship_gap]")


@pytest.mark.django_db
@pytest.mark.xfail(
    reason="Bearer bypass updates in Phase 5.4 — middleware allowlist keys on /api/projects/ not /api/v2/projects/"
)
def test_list_insights_bearer_readable():
    """GET /insights/ should accept Bearer tokens — xfail until Phase 5.4."""
    p = _make_project(slug="ins-bearer")
    ProjectContext.objects.create(
        project=p, context_type="insight", content="[test] hi", source="test"
    )
    anon_client = Client()
    resp = anon_client.get("/api/v2/insights/")
    # Middleware allowlist includes /api/insights/ but not /api/v2/insights/
    assert resp.status_code == 200  # currently 401


@pytest.mark.django_db
def test_clear_insights_200():
    p = _make_project(slug="ins-clear")
    ProjectContext.objects.create(
        project=p, context_type="insight", content="x", source="test"
    )
    c = _auth_client()
    resp = _post_json(c, "/api/v2/insights/clear/", {})
    assert resp.status_code == 200
    body = resp.json()
    assert "cleared" in body
    assert body["cleared"] >= 1


@pytest.mark.django_db
def test_dismiss_insight_200():
    p = _make_project(slug="ins-dismiss")
    ctx = ProjectContext.objects.create(
        project=p, context_type="insight", content="x", source="test"
    )
    c = _auth_client()
    resp = _delete(c, f"/api/v2/insights/{ctx.pk}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dismissed"] == ctx.pk
    assert not ProjectContext.objects.filter(pk=ctx.pk).exists()


@pytest.mark.django_db
def test_dismiss_insight_404():
    c = _auth_client()
    resp = _delete(c, "/api/v2/insights/999999/")
    assert resp.status_code == 404
    body = resp.json()
    assert body["status"] == 404
