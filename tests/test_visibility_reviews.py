"""Tokenless review read; authenticated-only submit."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from apps.reviews.models import ReviewRequest


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(
        username="owner@dimagi.com", email="owner@dimagi.com",
    )


def _review(owner, **kw):
    defaults = dict(
        run_id="demo-2026-06-09-001",
        narrative_slug="demo",
        gate="narrative-agreement",
        request_json={"narrative": "A story"},
        owner=owner,
    )
    defaults.update(kw)
    return ReviewRequest.objects.create(**defaults)


@override_settings(REQUIRE_AUTH=True)
def test_public_review_read_anonymous(owner):
    r = _review(owner, visibility="link")
    resp = Client().get(f"/api/reviews/{r.id}/")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(r.id)


@override_settings(REQUIRE_AUTH=True)
def test_private_review_404s_anonymous(owner):
    r = _review(owner, visibility="private")
    resp = Client().get(f"/api/reviews/{r.id}/")
    assert resp.status_code in (403, 404)


@override_settings(REQUIRE_AUTH=True)
def test_public_review_submit_blocked_for_anonymous(owner):
    r = _review(owner, visibility="link")
    resp = Client().post(
        f"/api/reviews/{r.id}/submit/",
        data={"response_json": {}},
        content_type="application/json",
    )
    assert resp.status_code in (401, 403)


@override_settings(REQUIRE_AUTH=True)
def test_review_submit_allowed_for_authenticated(owner):
    r = _review(owner, visibility="link")
    client = Client()
    client.force_login(owner)
    resp = client.post(
        f"/api/reviews/{r.id}/submit/",
        data={"response_json": {}},
        content_type="application/json",
    )
    assert resp.status_code == 200
