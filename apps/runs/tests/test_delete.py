"""Tests for the /api/ddd cascade-delete endpoints."""
from __future__ import annotations

import pytest
from django.test import Client

from apps.reviews.models import ReviewRequest
from apps.walkthroughs.models import Walkthrough

from .factories import make_review, make_user, make_walkthrough

pytestmark = pytest.mark.django_db

BASE = "/api/ddd"

NARR_JSON = {
    "gate": "narrative-agreement",
    "narrative": "Story line one.",
    "narration": [{"scene": 1, "id": "n1", "text": "x"}],
}


@pytest.fixture
def owner(db):
    return make_user()


@pytest.fixture
def client(owner):
    c = Client()
    c.force_login(owner)
    return c


def test_delete_run_removes_walkthroughs_and_reviews(client, owner):
    rid = "a-2026-06-01-001"
    make_walkthrough(owner, kind="video", run_id=rid, narrative_slug="a", role="hero_video")
    make_review(owner, run_id=rid, request_json={**NARR_JSON, "run_id": rid}, version=1)

    resp = client.delete(f"{BASE}/runs/{rid}/")
    assert resp.status_code == 204, resp.content
    assert not Walkthrough.objects.filter(run_id=rid).exists()
    assert not ReviewRequest.objects.filter(run_id=rid).exists()
    # Nothing left under the narrative.
    assert client.get(f"{BASE}/narratives/a/").status_code == 404


def test_delete_run_404(client):
    assert client.delete(f"{BASE}/runs/ghost-2026-01-01-001/").status_code == 404


def test_delete_version_removes_its_runs_and_story(client, owner):
    # v1 story review (its own gate run_id, no artifacts) ...
    version_review = make_review(
        owner,
        run_id="a-2026-05-31-001",
        request_json={**NARR_JSON, "run_id": "a-2026-05-31-001"},
        version=1,
    )
    # ... and a render stamped to it.
    render_rid = "a-2026-06-01-002"
    make_walkthrough(
        owner,
        kind="video",
        run_id=render_rid,
        narrative_slug="a",
        role="hero_video",
        narrative_review_id=version_review.id,
    )

    resp = client.delete(f"{BASE}/narratives/a/versions/1/")
    assert resp.status_code == 204, resp.content
    assert not Walkthrough.objects.filter(run_id=render_rid).exists()
    assert not ReviewRequest.objects.filter(id=version_review.id).exists()
    assert client.get(f"{BASE}/narratives/a/").status_code == 404


def test_delete_version_404(client, owner):
    make_walkthrough(owner, kind="video", run_id="a-2026-06-01-001", narrative_slug="a")
    # Narrative exists but has no version 9.
    assert client.delete(f"{BASE}/narratives/a/versions/9/").status_code == 404


def test_delete_narrative_removes_everything(client, owner):
    make_walkthrough(owner, kind="video", run_id="a-2026-06-01-001", narrative_slug="a")
    make_walkthrough(owner, kind="html", run_id="a-2026-06-02-002", narrative_slug="a")
    make_review(
        owner,
        run_id="a-2026-05-31-001",
        request_json={**NARR_JSON, "run_id": "a-2026-05-31-001"},
        version=1,
    )
    # An unrelated narrative must survive.
    make_walkthrough(owner, kind="video", run_id="b-2026-06-01-001", narrative_slug="b")

    resp = client.delete(f"{BASE}/narratives/a/")
    assert resp.status_code == 204, resp.content
    assert not Walkthrough.objects.filter(narrative_slug="a").exists()
    assert not ReviewRequest.objects.filter(run_id__startswith="a-").exists()
    assert client.get(f"{BASE}/narratives/a/").status_code == 404
    # Sibling untouched.
    assert client.get(f"{BASE}/narratives/b/").status_code == 200


def test_delete_narrative_404(client):
    assert client.delete(f"{BASE}/narratives/ghost/").status_code == 404
