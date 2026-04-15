"""Tests for WORKBENCH_WRITE_TOKEN Bearer bypass.

The LoginRequiredMiddleware should let machine callers POST to a narrow
set of write endpoints (/api/projects/*/actions/ and /api/projects/*/context/)
using ``Authorization: Bearer <WORKBENCH_WRITE_TOKEN>``. Everything else
(read endpoints, other paths) still falls through to the OAuth gate.
"""
import json

import pytest
from django.test import Client, override_settings

from apps.projects.models import Project


TEST_TOKEN = "test-token-123"


@pytest.fixture
def project(db):
    return Project.objects.create(
        name="canopy-web",
        slug="canopy-web",
        repo_url="https://github.com/jjackson/canopy-web",
        status="active",
        visibility="public",
    )


def _bearer(token: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@override_settings(REQUIRE_AUTH=True, WORKBENCH_WRITE_TOKEN=TEST_TOKEN)
def test_actions_post_with_valid_bearer_succeeds(project):
    client = Client()
    resp = client.post(
        f"/api/projects/{project.slug}/actions/",
        data=json.dumps(
            {
                "skill_name": "commit",
                "status": "completed",
                "started_at": "2026-04-14T12:00:00Z",
            }
        ),
        content_type="application/json",
        **_bearer(TEST_TOKEN),
    )
    assert resp.status_code == 201, resp.content


@override_settings(REQUIRE_AUTH=True, WORKBENCH_WRITE_TOKEN=TEST_TOKEN)
def test_actions_post_without_bearer_is_rejected(project):
    client = Client()
    resp = client.post(
        f"/api/projects/{project.slug}/actions/",
        data=json.dumps(
            {
                "skill_name": "commit",
                "status": "completed",
                "started_at": "2026-04-14T12:00:00Z",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authentication required"}


@override_settings(REQUIRE_AUTH=True, WORKBENCH_WRITE_TOKEN=TEST_TOKEN)
def test_actions_post_with_wrong_bearer_is_rejected(project):
    client = Client()
    resp = client.post(
        f"/api/projects/{project.slug}/actions/",
        data=json.dumps(
            {
                "skill_name": "commit",
                "status": "completed",
                "started_at": "2026-04-14T12:00:00Z",
            }
        ),
        content_type="application/json",
        **_bearer("not-the-real-token"),
    )
    assert resp.status_code == 401


@override_settings(REQUIRE_AUTH=True, WORKBENCH_WRITE_TOKEN=TEST_TOKEN)
def test_context_post_with_valid_bearer_succeeds(project):
    client = Client()
    resp = client.post(
        f"/api/projects/{project.slug}/context/",
        data=json.dumps(
            {"context_type": "current_work", "content": "hook test", "source": "hook"}
        ),
        content_type="application/json",
        **_bearer(TEST_TOKEN),
    )
    assert resp.status_code == 201, resp.content


@override_settings(REQUIRE_AUTH=True, WORKBENCH_WRITE_TOKEN=TEST_TOKEN)
def test_read_projects_list_with_bearer_is_still_rejected(project):
    """Bearer only covers the allowlisted write endpoints, not reads."""
    client = Client()
    resp = client.get("/api/projects/", **_bearer(TEST_TOKEN))
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authentication required"}


@override_settings(REQUIRE_AUTH=True, WORKBENCH_WRITE_TOKEN=TEST_TOKEN)
def test_actions_summary_with_bearer_is_rejected(project):
    """The Bearer bypass is scoped to exact /actions/ and /context/ suffixes —
    nested read endpoints like /actions/summary/ should still require OAuth."""
    client = Client()
    resp = client.get(
        f"/api/projects/{project.slug}/actions/summary/", **_bearer(TEST_TOKEN)
    )
    assert resp.status_code == 401


@override_settings(REQUIRE_AUTH=True, WORKBENCH_WRITE_TOKEN="")
def test_bearer_bypass_disabled_when_token_unset(project):
    """If WORKBENCH_WRITE_TOKEN is empty, the bypass is disabled entirely
    — even if the caller sends a Bearer header, we require OAuth."""
    client = Client()
    resp = client.post(
        f"/api/projects/{project.slug}/actions/",
        data=json.dumps(
            {
                "skill_name": "commit",
                "status": "completed",
                "started_at": "2026-04-14T12:00:00Z",
            }
        ),
        content_type="application/json",
        **_bearer("anything"),
    )
    assert resp.status_code == 401


@override_settings(REQUIRE_AUTH=True, WORKBENCH_WRITE_TOKEN=TEST_TOKEN)
def test_bearer_does_not_bypass_non_projects_api(project):
    """Paths outside /api/projects/ do not honor the token bypass."""
    client = Client()
    resp = client.get("/api/skills/", **_bearer(TEST_TOKEN))
    assert resp.status_code == 401
