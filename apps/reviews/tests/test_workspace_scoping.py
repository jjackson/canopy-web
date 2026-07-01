"""End-to-end workspace scoping of the /api/reviews surface.

Mirrors apps/agents/tests/test_workspace_scoping.py: create with no workspace →
default workspace + creator membership (so the unchanged orchestrator keeps
working); domain teammates auto-join and see it in the list; outsiders don't.

PLUS the visibility invariant that scoping must NOT break: an anonymous caller
can still GET a visibility=link review detail after scoping, and submitting a
decision still requires a login.
"""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from apps.reviews.models import ReviewRequest
from apps.workspaces.services import DEFAULT_WORKSPACE_SLUG

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture(autouse=True)
def _domain(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = "dimagi.com"


def _user(email, **kw):
    return User.objects.create(username=email, email=email, **kw)


def _client(u):
    c = Client()
    c.force_login(u)
    return c


def _create_review(client, **body):
    payload = {
        "request_json": {"run_id": "demo-2026-06-30-001", "gate": "narrative-agreement", "narrative": "A story"},
        "visibility": "link",
    }
    payload.update(body)
    return client.post("/api/reviews/", data=json.dumps(payload), content_type="application/json")


def test_create_without_workspace_assigns_default_and_keeps_creator_in():
    jj = _user("jj@dimagi.com", is_superuser=True)  # the human who minted the PAT
    resp = _create_review(_client(jj))
    assert resp.status_code == 201
    review = ReviewRequest.objects.get(pk=resp.json()["id"])
    assert review.workspace_id == DEFAULT_WORKSPACE_SLUG
    # The creator still sees it in the dashboard list.
    listing = _client(jj).get("/api/reviews/").json()
    assert any(r["id"] == str(review.id) for r in listing)


def test_domain_teammate_auto_joins_and_sees_review():
    jj = _user("jj@dimagi.com", is_superuser=True)
    resp = _create_review(_client(jj))
    rid = resp.json()["id"]
    teammate = _user("t@dimagi.com")  # never explicitly added
    listing = _client(teammate).get("/api/reviews/").json()
    assert any(r["id"] == rid for r in listing)


def test_outsider_does_not_see_workspace_scoped_review():
    jj = _user("jj@dimagi.com", is_superuser=True)
    resp = _create_review(_client(jj))
    rid = resp.json()["id"]
    outsider = _user("x@other.com")
    listing = _client(outsider).get("/api/reviews/").json()
    assert all(r["id"] != rid for r in listing)


@override_settings(REQUIRE_AUTH=True)
def test_anonymous_can_still_read_public_link_review_after_scoping():
    """The detail read path must keep serving visibility=link reviews to anon —
    scoping applies only to the authenticated LIST, never the single-object read."""
    jj = _user("jj@dimagi.com", is_superuser=True)
    resp = _create_review(_client(jj), visibility="link")
    rid = resp.json()["id"]
    review = ReviewRequest.objects.get(pk=rid)
    assert review.workspace_id == DEFAULT_WORKSPACE_SLUG  # it IS workspace-scoped
    anon = Client().get(f"/api/reviews/{rid}/")
    assert anon.status_code == 200
    assert anon.json()["id"] == rid


@override_settings(REQUIRE_AUTH=True)
def test_submit_still_requires_auth_after_scoping():
    jj = _user("jj@dimagi.com", is_superuser=True)
    resp = _create_review(_client(jj), visibility="link")
    rid = resp.json()["id"]
    anon = Client().post(
        f"/api/reviews/{rid}/submit/",
        data=json.dumps({"response_json": {}}),
        content_type="application/json",
    )
    assert anon.status_code in (401, 403)
