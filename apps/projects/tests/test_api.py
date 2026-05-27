"""Contract tests for the projects + insights Ninja surface.

These tests verify:
- Auth: 401 for anonymous, 200 for force_login sessions.
- Status codes: 200 list, 201 create, 204 delete, 404 not-found, 409 conflict.
- Round-trip: response bodies validate through the corresponding Pydantic schema.
- Bearer bypass: write/read endpoints accept Authorization: Bearer tokens.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

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
    resp = c.get("/api/projects/")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] >= 1
    # Round-trip the first item through ProjectListOut
    ProjectListOut.model_validate(body["items"][0])


@pytest.mark.django_db
def test_list_projects_401_anonymous():
    c = Client()
    resp = c.get("/api/projects/")
    assert resp.status_code == 401
    body = resp.json()
    assert body["status"] == 401


@pytest.mark.django_db
def test_list_projects_pagination():
    user = _make_user()
    for i in range(5):
        _make_project(slug=f"proj-{i}", name=f"Project {i}")
    c = _auth_client(user)
    resp = c.get("/api/projects/?offset=0&limit=2")
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
    resp = c.get("/api/projects/slugs/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    slugs = [item["slug"] for item in body]
    assert "my-slug" in slugs
    # Round-trip through schema
    ProjectSlugOut.model_validate(body[0])


@pytest.mark.django_db
@override_settings(REQUIRE_AUTH=True)
def test_get_project_slugs_pat_readable():
    """Anonymous request carrying a valid PAT should authenticate and 200."""
    from apps.tokens.models import PersonalToken

    user = User.objects.create_user(username="bot", email="bot@dimagi-ai.com")
    raw, _ = PersonalToken.create_for_user(user=user, label="slug-reader")
    _make_project()
    anon_client = Client()
    resp = anon_client.get(
        "/api/projects/slugs/",
        HTTP_AUTHORIZATION=f"Bearer {raw}",
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# create_project
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_project_201():
    c = _auth_client()
    resp = _post_json(c, "/api/projects/", {
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
    resp = _post_json(c, "/api/projects/", {
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
    resp = c.get("/api/projects/detail-slug/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "detail-slug"
    ProjectDetailOut.model_validate(body)


@pytest.mark.django_db
def test_get_project_404_problem_json():
    c = _auth_client()
    resp = c.get("/api/projects/does-not-exist/")
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
    resp = _patch_json(c, "/api/projects/patchme/", {"status": "archived"})
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
    resp = _delete(c, "/api/projects/deleteme/")
    assert resp.status_code == 204
    assert not Project.objects.filter(slug="deleteme").exists()


@pytest.mark.django_db
def test_delete_project_404():
    c = _auth_client()
    resp = _delete(c, "/api/projects/no-such-project/")
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
    resp = c.get("/api/projects/ctx-proj/context/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["context_type"] == "current_work"


@pytest.mark.django_db
def test_create_context_201():
    _make_project(slug="ctx-create")
    c = _auth_client()
    resp = _post_json(c, "/api/projects/ctx-create/context/", {
        "context_type": "note",
        "content": "Some note content",
        "source": "test-suite",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["context_type"] == "note"
    assert body["content"] == "Some note content"


@pytest.mark.django_db
@override_settings(REQUIRE_AUTH=True)
def test_create_context_pat_writable():
    """Anonymous request with a valid PAT should be allowed to POST /context/."""
    from apps.tokens.models import PersonalToken

    user = User.objects.create_user(username="bot-ctx", email="ctx@dimagi-ai.com")
    raw, _ = PersonalToken.create_for_user(user=user, label="ctx-writer")
    _make_project(slug="bearer-ctx-test")
    anon_client = Client()
    resp = anon_client.post(
        "/api/projects/bearer-ctx-test/context/",
        data=json.dumps({"context_type": "note", "content": "Bearer note", "source": "machine-caller"}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw}",
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_get_context_latest_200():
    p = _make_project(slug="ctx-latest")
    ProjectContext.objects.create(
        project=p, context_type="summary", content="Summary text", source="test"
    )
    c = _auth_client()
    resp = c.get("/api/projects/ctx-latest/context/latest/")
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
        started_at=dt.datetime(2026, 5, 1, tzinfo=dt.UTC),
    )
    c = _auth_client()
    resp = c.get("/api/projects/act-proj/actions/")
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
        started_at=dt.datetime(2026, 5, 1, tzinfo=dt.UTC),
    )
    ProjectAction.objects.create(
        project=p,
        skill_name="qa",
        status="started",
        started_at=dt.datetime(2026, 5, 2, tzinfo=dt.UTC),
    )
    c = _auth_client()
    resp = c.get("/api/projects/act-filter/actions/?skill=qa")
    assert resp.status_code == 200
    body = resp.json()
    assert all(a["skill_name"] == "qa" for a in body)


@pytest.mark.django_db
def test_create_action_201():
    _make_project(slug="act-create")
    c = _auth_client()
    resp = _post_json(c, "/api/projects/act-create/actions/", {
        "skill_name": "session-review",
        "status": "started",
        "started_at": "2026-05-26T10:00:00Z",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["skill_name"] == "session-review"


@pytest.mark.django_db
@override_settings(REQUIRE_AUTH=True)
def test_create_action_pat_writable():
    """POST /actions/ should accept a PAT bearer (anonymous + no PAT = 401)."""
    from apps.tokens.models import PersonalToken

    user = User.objects.create_user(username="bot-act", email="act@dimagi-ai.com")
    raw, _ = PersonalToken.create_for_user(user=user, label="action-writer")
    _make_project(slug="bearer-act-test")
    anon_client = Client()
    resp = _post_json(
        anon_client,
        "/api/projects/bearer-act-test/actions/",
        {"skill_name": "commit", "status": "completed", "started_at": "2026-05-26T10:00:00Z"},
    )
    # Without bearer: 401
    assert resp.status_code == 401

    # With PAT: 201
    resp2 = anon_client.post(
        "/api/projects/bearer-act-test/actions/",
        data=json.dumps({"skill_name": "commit", "status": "completed", "started_at": "2026-05-26T10:00:00Z"}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw}",
    )
    assert resp2.status_code == 201


@pytest.mark.django_db
def test_get_actions_summary_200():
    p = _make_project(slug="act-summary")
    ProjectAction.objects.create(
        project=p,
        skill_name="session-review",
        status="completed",
        started_at=dt.datetime(2026, 5, 1, tzinfo=dt.UTC),
    )
    ProjectAction.objects.create(
        project=p,
        skill_name="session-review",
        status="started",
        started_at=dt.datetime(2026, 5, 2, tzinfo=dt.UTC),
    )
    c = _auth_client()
    resp = c.get("/api/projects/act-summary/actions/summary/")
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
    resp = _post_json(c, "/api/projects/batch-context/", {
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
def test_batch_context_authenticated_writable():
    """POST /batch-context/ accepts authenticated session requests."""
    _make_project(slug="bearer-test")
    c = _auth_client()
    resp = _post_json(c, "/api/projects/batch-context/", {
        "updates": {
            "bearer-test": [
                {"context_type": "current_work", "content": "Bearer test", "source": "test"}
            ]
        }
    })
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
    resp = c.get("/api/insights/")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] >= 1
    InsightOut.model_validate(body["items"][0])


@pytest.mark.django_db
def test_list_insights_401_anonymous():
    c = Client()
    resp = c.get("/api/insights/")
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
    resp = c.get("/api/insights/?category=ship_gap")
    assert resp.status_code == 200
    body = resp.json()
    for item in body["items"]:
        assert item["content"].startswith("[ship_gap]")


@pytest.mark.django_db
@override_settings(REQUIRE_AUTH=True)
def test_list_insights_pat_readable():
    """GET /insights/ should accept a valid PAT."""
    from apps.tokens.models import PersonalToken

    user = User.objects.create_user(username="bot-ins", email="ins@dimagi-ai.com")
    raw, _ = PersonalToken.create_for_user(user=user, label="insights-reader")
    p = _make_project(slug="ins-bearer")
    ProjectContext.objects.create(
        project=p, context_type="insight", content="[test] hi", source="test"
    )
    anon_client = Client()
    resp = anon_client.get("/api/insights/", HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_clear_insights_200():
    p = _make_project(slug="ins-clear")
    ProjectContext.objects.create(
        project=p, context_type="insight", content="x", source="test"
    )
    c = _auth_client()
    resp = _post_json(c, "/api/insights/clear/", {})
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
    resp = _delete(c, f"/api/insights/{ctx.pk}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dismissed"] == ctx.pk
    assert not ProjectContext.objects.filter(pk=ctx.pk).exists()


@pytest.mark.django_db
def test_dismiss_insight_404():
    c = _auth_client()
    resp = _delete(c, "/api/insights/999999/")
    assert resp.status_code == 404
    body = resp.json()
    assert body["status"] == 404
