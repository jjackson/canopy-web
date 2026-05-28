"""Contract tests for the reviews Ninja surface (/api/reviews/).

Covers:
  POST   /api/reviews/              — create; returns id + url + share_token
  GET    /api/reviews/<id>/         — owner sees share_token; ?t= unauth OK; bad token → 404
  POST   /api/reviews/<id>/submit/  — writes response_json, flips status, stamps resolved_at
  Round-trip: create → get reflects request_json correctly
  Submit gate: already-resolved → 403
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.reviews.models import ReviewRequest

User = get_user_model()

BASE = "/api/reviews"

# ---------------------------------------------------------------------------
# Minimal valid request_json matching the canopy ReviewRequest schema
# ---------------------------------------------------------------------------

SAMPLE_REQUEST_JSON = {
    "schema_version": 1,
    "run_id": "run-abc-123",
    "gate": "pre_ship",
    "video": {"walkthrough_id": "walk-001", "url": "https://example.com/w/001"},
    "decisions": [
        {
            "id": "d1",
            "prompt": "Should we ship?",
            "options": ["yes", "no", "defer"],
            "recommended": "yes",
            "class": "go_no_go",
        }
    ],
    "narration": [{"scene": 1, "id": "n1", "text": "The demo starts here."}],
    "autonomous_audit": ["No regressions detected."],
}

SAMPLE_RESPONSE_JSON = {
    "decisions": {"d1": "yes"},
    "narration_edits": {"n1": "Updated narration text."},
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        username="owner@dimagi.com",
        email="owner@dimagi.com",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="other@dimagi.com",
        email="other@dimagi.com",
    )


@pytest.fixture
def auth_client(owner):
    c = Client()
    c.force_login(owner)
    return c


@pytest.fixture
def other_client(other_user):
    c = Client()
    c.force_login(other_user)
    return c


def _make_review(owner, **kwargs) -> ReviewRequest:
    defaults = dict(
        run_id="run-test",
        gate="pre_ship",
        request_json=SAMPLE_REQUEST_JSON,
        visibility="link",
    )
    defaults.update(kwargs)
    return ReviewRequest.objects.create(owner=owner, **defaults)


# ---------------------------------------------------------------------------
# 1. create returns id + url + share_token
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_returns_id_url_share_token(auth_client):
    resp = auth_client.post(
        f"{BASE}/",
        data={"request_json": SAMPLE_REQUEST_JSON, "visibility": "link"},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert "id" in body
    assert "url" in body
    assert "share_token" in body
    assert body["share_token"] is not None
    # URL should reference the review id and include the token
    assert body["id"] in body["url"]
    assert body["share_token"] in body["url"]


# ---------------------------------------------------------------------------
# 2. GET by owner returns full record including share_token
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_by_owner_includes_share_token(auth_client, owner):
    review = _make_review(owner, visibility="link")
    review.ensure_share_token()

    resp = auth_client.get(f"{BASE}/{review.id}/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["id"] == str(review.id)
    assert body["is_owner"] is True
    assert body["share_token"] == review.share_token
    assert body["status"] == "pending"


# ---------------------------------------------------------------------------
# 3. GET with valid ?t= (unauthenticated) returns data WITHOUT share_token
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_with_valid_token_unauth_share_token_exposed(owner):
    review = _make_review(owner, visibility="link")
    token = review.ensure_share_token()

    c = Client()  # unauthenticated
    resp = c.get(f"{BASE}/{review.id}/?t={token}")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "pending"
    # share_token is exposed to link-token holders (they demonstrably have it
    # and need it to re-poll or submit)
    assert body["share_token"] == token
    # is_owner is False — they are not the DB owner, just a link-token holder
    assert body["is_owner"] is False


@pytest.mark.django_db
def test_get_with_valid_token_unauth_returns_data(owner):
    """An unauthenticated caller with a valid ?t= can read the review."""
    review = _make_review(owner, visibility="link")
    token = review.ensure_share_token()

    c = Client()
    resp = c.get(f"{BASE}/{review.id}/?t={token}")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["run_id"] == review.run_id
    assert body["gate"] == review.gate


# ---------------------------------------------------------------------------
# 4. GET with bad / no token (unauthenticated) → 404
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_bad_token_unauth_returns_404(owner):
    review = _make_review(owner, visibility="link")
    review.ensure_share_token()

    c = Client()
    resp = c.get(f"{BASE}/{review.id}/?t=WRONG_TOKEN")
    assert resp.status_code == 404, resp.content


@pytest.mark.django_db
def test_get_no_token_unauth_returns_404(owner):
    review = _make_review(owner, visibility="link")
    review.ensure_share_token()

    c = Client()
    resp = c.get(f"{BASE}/{review.id}/")
    assert resp.status_code == 404, resp.content


@pytest.mark.django_db
def test_get_nonexistent_review_404(auth_client):
    bogus = uuid.uuid4()
    resp = auth_client.get(f"{BASE}/{bogus}/")
    assert resp.status_code == 404, resp.content
    body = resp.json()
    assert body.get("type", "").endswith("/not-found")


# ---------------------------------------------------------------------------
# 5. submit writes response_json + flips status + stamps resolved_at
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_resolves_review(auth_client, owner):
    review = _make_review(owner, visibility="link")
    review.ensure_share_token()

    resp = auth_client.post(
        f"{BASE}/{review.id}/submit/",
        data={"response_json": SAMPLE_RESPONSE_JSON},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["response_json"] == SAMPLE_RESPONSE_JSON
    assert body["resolved_at"] is not None

    # Verify DB state
    review.refresh_from_db()
    assert review.status == ReviewRequest.STATUS_RESOLVED
    assert review.response_json == SAMPLE_RESPONSE_JSON
    assert review.resolved_at is not None


# ---------------------------------------------------------------------------
# 6. submit via valid ?t= (unauth) also works
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_via_link_token_works(owner):
    review = _make_review(owner, visibility="link")
    token = review.ensure_share_token()

    c = Client()
    resp = c.post(
        f"{BASE}/{review.id}/submit/?t={token}",
        data={"response_json": SAMPLE_RESPONSE_JSON},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "resolved"


# ---------------------------------------------------------------------------
# 7. submit is gated — bad/no token unauth → 404
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_bad_token_unauth_returns_404(owner):
    review = _make_review(owner, visibility="link")
    review.ensure_share_token()

    c = Client()
    resp = c.post(
        f"{BASE}/{review.id}/submit/?t=WRONG",
        data={"response_json": SAMPLE_RESPONSE_JSON},
        content_type="application/json",
    )
    assert resp.status_code == 404, resp.content


# ---------------------------------------------------------------------------
# 8. re-submission on already-resolved → 403
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_already_resolved_returns_403(auth_client, owner):
    review = _make_review(owner, visibility="link")
    review.status = ReviewRequest.STATUS_RESOLVED
    review.response_json = SAMPLE_RESPONSE_JSON
    review.resolved_at = timezone.now()
    review.save()

    resp = auth_client.post(
        f"{BASE}/{review.id}/submit/",
        data={"response_json": {"decisions": {}, "narration_edits": {}}},
        content_type="application/json",
    )
    assert resp.status_code == 403, resp.content
    body = resp.json()
    assert body.get("type", "").endswith("/forbidden")


# ---------------------------------------------------------------------------
# 9. request_json round-trips: create → get reflects the same JSON
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_request_json_round_trips(auth_client, owner):
    resp = auth_client.post(
        f"{BASE}/",
        data={"request_json": SAMPLE_REQUEST_JSON, "visibility": "link"},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    rid = resp.json()["id"]

    resp2 = auth_client.get(f"{BASE}/{rid}/")
    assert resp2.status_code == 200, resp2.content
    body = resp2.json()
    assert body["request_json"] == SAMPLE_REQUEST_JSON
    assert body["run_id"] == SAMPLE_REQUEST_JSON["run_id"]
    assert body["gate"] == SAMPLE_REQUEST_JSON["gate"]


# ---------------------------------------------------------------------------
# 10. non-owner authenticated user can still read (team-internal access)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_non_owner_authenticated_can_read(other_client, owner):
    review = _make_review(owner, visibility="private")
    review.ensure_share_token()

    resp = other_client.get(f"{BASE}/{review.id}/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["is_owner"] is False
    # Non-owner does not see share_token
    assert body["share_token"] is None


# ---------------------------------------------------------------------------
# 11. submit on a private review by an authenticated NON-owner is blocked
#
#     Write gate semantics: private visibility means the review is readable
#     by any dimagi-authenticated user, but submit (write) requires being the
#     owner OR holding a valid ?t= share token.  A non-owner authenticated
#     session without a token must not be able to resolve the review.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_private_review_by_non_owner_is_blocked(other_client, owner):
    """Authenticated non-owner without ?t= cannot submit a private review."""
    review = _make_review(owner, visibility="private")
    review.ensure_share_token()

    resp = other_client.post(
        f"{BASE}/{review.id}/submit/",
        data={"response_json": SAMPLE_RESPONSE_JSON},
        content_type="application/json",
    )
    # Must be blocked — 403 or 404 (endpoint returns 404 to avoid leaking existence)
    assert resp.status_code in (403, 404), (
        f"Expected 403 or 404 but got {resp.status_code}: {resp.content}"
    )

    # Review must NOT have been resolved in the database
    review.refresh_from_db()
    assert review.status == ReviewRequest.STATUS_PENDING, (
        "Review should still be pending after blocked submit attempt"
    )
    assert review.response_json is None
