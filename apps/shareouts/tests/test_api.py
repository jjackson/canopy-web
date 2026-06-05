"""Contract tests for the /api/shareouts Ninja surface.

Verifies: auth (401 anon, PAT writable), batch create (201), idempotent
replace per (project, period, source), roll-up rows (null project), and
GET date/project filters.
"""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from apps.projects.models import Project
from apps.shareouts.models import Shareout
from apps.shareouts.schemas import ShareoutOut

User = get_user_model()


def _make_user(username="alice", email="alice@dimagi.com"):
    return User.objects.create_user(username=username, email=email, password="pw")


def _make_project(slug="canopy-web", name="canopy-web"):
    return Project.objects.create(name=name, slug=slug, status="active")


def _auth_client(user=None):
    c = Client()
    c.force_login(user or _make_user())
    return c


def _post(client, data):
    return client.post(
        "/api/shareouts/", data=json.dumps(data), content_type="application/json"
    )


def _item(**overrides):
    base = {
        "project_slug": "canopy-web",
        "period_start": "2026-06-03T09:00:00Z",
        "period_end": "2026-06-03T17:30:00Z",
        "title": "Shipped the shareout feed",
        "summary": "TL;DR",
        "content": "## What\nBuilt it.\n\n## Why\nTeammates need it.",
        "links": [{"label": "PR #1", "url": "https://github.com/x/y/pull/1"}],
        "all_prs": [
            {"number": 1, "title": "Add the feed", "url": "https://github.com/x/y/pull/1", "state": "MERGED"},
            {"number": 2, "title": "Fix a bug", "url": "https://github.com/x/y/pull/2", "state": "OPEN"},
        ],
        "author": "jjackson",
        "source": "canopy:shareout@2026-06-04T00:00:00",
    }
    base.update(overrides)
    return base


# --- auth -----------------------------------------------------------------


@pytest.mark.django_db
def test_list_401_anonymous():
    resp = Client().get("/api/shareouts/")
    assert resp.status_code == 401


@pytest.mark.django_db
@override_settings(REQUIRE_AUTH=True)
def test_post_pat_writable():
    from apps.tokens.models import PersonalToken

    user = User.objects.create_user(username="bot", email="bot@dimagi-ai.com")
    raw, _ = PersonalToken.create_for_user(user=user, label="shareout-writer")
    _make_project()
    resp = Client().post(
        "/api/shareouts/",
        data=json.dumps({"shareouts": [_item()]}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw}",
    )
    assert resp.status_code == 201
    assert resp.json()["created"] == 1


# --- create ---------------------------------------------------------------


@pytest.mark.django_db
def test_post_creates_rows():
    _make_project()
    c = _auth_client()
    resp = _post(c, {"shareouts": [_item()]})
    assert resp.status_code == 201
    body = resp.json()
    assert body == {"created": 1, "replaced": 0, "skipped": 0}
    assert Shareout.objects.count() == 1


@pytest.mark.django_db
def test_post_rollup_has_null_project():
    c = _auth_client()
    resp = _post(c, {"shareouts": [_item(project_slug=None, title="Roll-up")]})
    assert resp.status_code == 201
    assert resp.json()["created"] == 1
    row = Shareout.objects.get()
    assert row.project_id is None


@pytest.mark.django_db
def test_post_unknown_slug_skipped():
    c = _auth_client()
    resp = _post(c, {"shareouts": [_item(project_slug="does-not-exist")]})
    assert resp.status_code == 201
    assert resp.json() == {"created": 0, "replaced": 0, "skipped": 1}
    assert Shareout.objects.count() == 0


@pytest.mark.django_db
def test_post_idempotent_replace_same_group():
    _make_project()
    c = _auth_client()
    _post(c, {"shareouts": [_item(content="v1")]})
    resp = _post(c, {"shareouts": [_item(content="v2")]})
    assert resp.status_code == 201
    assert resp.json() == {"created": 1, "replaced": 1, "skipped": 0}
    assert Shareout.objects.count() == 1
    assert Shareout.objects.get().content == "v2"


@pytest.mark.django_db
def test_post_different_period_does_not_replace():
    _make_project()
    c = _auth_client()
    _post(c, {"shareouts": [_item(period_start="2026-06-02T09:00:00Z", period_end="2026-06-02T17:00:00Z")]})
    _post(c, {"shareouts": [_item(period_start="2026-06-03T09:00:00Z", period_end="2026-06-03T17:00:00Z")]})
    assert Shareout.objects.count() == 2


# --- list -----------------------------------------------------------------


@pytest.mark.django_db
def test_list_returns_rows_and_validates():
    _make_project()
    c = _auth_client()
    _post(c, {"shareouts": [_item()]})
    resp = c.get("/api/shareouts/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    item = ShareoutOut.model_validate(body["items"][0])
    assert len(item.all_prs) == 2
    assert item.all_prs[0].number == 1


@pytest.mark.django_db
def test_list_project_filter_excludes_others():
    _make_project(slug="canopy-web")
    _make_project(slug="ace", name="ace")
    c = _auth_client()
    _post(c, {"shareouts": [_item(project_slug="canopy-web")]})
    _post(c, {"shareouts": [_item(project_slug="ace")]})
    resp = c.get("/api/shareouts/?project=ace")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["project_slug"] == "ace"


@pytest.mark.django_db
def test_list_date_filter():
    _make_project()
    c = _auth_client()
    _post(c, {"shareouts": [_item(period_start="2026-05-01T09:00:00Z", period_end="2026-05-01T17:00:00Z")]})
    _post(c, {"shareouts": [_item(period_start="2026-06-03T09:00:00Z", period_end="2026-06-03T17:00:00Z")]})
    resp = c.get("/api/shareouts/?date_from=2026-06-01")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["period_start"].startswith("2026-06-03")
