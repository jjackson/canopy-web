"""Workspace scoping for the /api/ddd read-model + cascade deletes.

A member of workspace A must never see, read, or delete workspace B's narratives
and runs — the DDD surface joins Walkthrough + ReviewRequest, both now
workspace-owned. Mirrors apps/agents/tests/test_workspace_scoping.py.
"""
from __future__ import annotations

import pytest
from django.test import Client

from apps.reviews.models import ReviewRequest
from apps.walkthroughs.models import Walkthrough

from .factories import (
    add_member,
    make_review,
    make_user,
    make_walkthrough,
    make_workspace,
)

pytestmark = pytest.mark.django_db

BASE = "/api/ddd"

NARR = {
    "gate": "narrative-agreement",
    "narrative": "Story line one.",
    "narration": [{"scene": 1, "id": "n1", "text": "x"}],
}

A_RUN = "alpha-2026-06-01-001"
B_RUN = "bravo-2026-06-01-001"


@pytest.fixture
def two_tenants(db):
    ua = make_user("a@dimagi.com")
    ub = make_user("b@dimagi.com")
    ws_a = make_workspace("ws-a")
    ws_b = make_workspace("ws-b")
    add_member(ws_a, ua)
    add_member(ws_b, ub)
    # Workspace A: one narrative "alpha".
    make_walkthrough(
        ua, kind="video", run_id=A_RUN, narrative_slug="alpha",
        role="hero_video", workspace=ws_a,
    )
    make_review(
        ua, run_id=A_RUN, version=1,
        request_json={**NARR, "run_id": A_RUN}, workspace=ws_a,
    )
    # Workspace B: one narrative "bravo".
    make_walkthrough(
        ub, kind="video", run_id=B_RUN, narrative_slug="bravo",
        role="hero_video", workspace=ws_b,
    )
    make_review(
        ub, run_id=B_RUN, version=1,
        request_json={**NARR, "run_id": B_RUN}, workspace=ws_b,
    )
    return ua, ub


def _client(u):
    c = Client()
    c.force_login(u)
    return c


def test_list_narratives_is_scoped_to_members_workspace(two_tenants):
    ua, ub = two_tenants
    a_slugs = {n["slug"] for n in _client(ua).get(f"{BASE}/narratives/").json()}
    b_slugs = {n["slug"] for n in _client(ub).get(f"{BASE}/narratives/").json()}
    assert a_slugs == {"alpha"}
    assert b_slugs == {"bravo"}


def test_cross_workspace_narrative_detail_404(two_tenants):
    ua, _ = two_tenants
    ca = _client(ua)
    assert ca.get(f"{BASE}/narratives/bravo/").status_code == 404  # B's, hidden
    assert ca.get(f"{BASE}/narratives/alpha/").status_code == 200  # own, visible


def test_cross_workspace_run_detail_404(two_tenants):
    ua, _ = two_tenants
    ca = _client(ua)
    assert ca.get(f"{BASE}/runs/{B_RUN}/").status_code == 404
    assert ca.get(f"{BASE}/runs/{A_RUN}/").status_code == 200


def test_cross_workspace_delete_run_404_and_rows_survive(two_tenants):
    ua, _ = two_tenants
    assert _client(ua).delete(f"{BASE}/runs/{B_RUN}/").status_code == 404
    # A member of A can't reach across the tenant boundary to delete B's rows.
    assert Walkthrough.objects.filter(run_id=B_RUN).exists()
    assert ReviewRequest.objects.filter(run_id=B_RUN).exists()


def test_cross_workspace_delete_narrative_404_and_rows_survive(two_tenants):
    ua, _ = two_tenants
    assert _client(ua).delete(f"{BASE}/narratives/bravo/").status_code == 404
    assert Walkthrough.objects.filter(narrative_slug="bravo").exists()
    assert ReviewRequest.objects.filter(run_id=B_RUN).exists()


def test_visibility_cascade_does_not_cross_workspace(two_tenants):
    ua, _ = two_tenants
    resp = _client(ua).patch(
        f"{BASE}/narratives/bravo/visibility/",
        data='{"visibility": "link"}',
        content_type="application/json",
    )
    # Nothing in A's scope matches "bravo", so the cascade flips zero rows and
    # B's private artifacts stay private.
    assert resp.status_code == 200
    body = resp.json()
    assert body["walkthroughs_updated"] == 0
    assert body["reviews_updated"] == 0
    assert not Walkthrough.objects.filter(
        narrative_slug="bravo", visibility="link"
    ).exists()
