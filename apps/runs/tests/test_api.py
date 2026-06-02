"""Contract tests for the /api/ddd surface."""
from __future__ import annotations

import pytest
from django.test import Client

from .factories import make_review, make_user, make_walkthrough

pytestmark = pytest.mark.django_db

BASE = "/api/ddd"


@pytest.fixture
def owner(db):
    return make_user()


@pytest.fixture
def client(owner):
    c = Client()
    c.force_login(owner)
    return c


def test_list_narratives(client, owner):
    make_walkthrough(owner, kind="video", run_id="a-2026-06-01-001", feature="a")
    make_walkthrough(owner, kind="html", run_id="a-2026-06-02-002", feature="a")
    resp = client.get(f"{BASE}/narratives/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert len(body) == 1
    assert body[0]["slug"] == "a"
    assert body[0]["run_count"] == 2


def test_narrative_detail(client, owner):
    make_walkthrough(owner, kind="video", run_id="a-2026-06-01-001", feature="a")
    resp = client.get(f"{BASE}/narratives/a/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["slug"] == "a"
    assert [r["run_id"] for r in body["runs"]] == ["a-2026-06-01-001"]


def test_narrative_detail_404(client):
    assert client.get(f"{BASE}/narratives/ghost/").status_code == 404


def test_run_package(client, owner):
    rid = "a-2026-06-01-001"
    vid = make_walkthrough(owner, kind="video", run_id=rid, role="hero_video")
    make_walkthrough(owner, kind="html", run_id=rid, role="docs")
    make_review(
        owner,
        run_id=rid,
        request_json={
            "run_id": rid,
            "gate": "narrative-agreement",
            "narrative": "Story line one.",
            "narration": [{"scene": 1, "id": "n1", "text": "x"}],
        },
    )
    resp = client.get(f"{BASE}/runs/{rid}/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["video"]["id"] == str(vid.id)
    assert body["deck"] is not None
    assert body["narrative"]["story"] == "Story line one."
    assert len(body["all_artifacts"]) == 2


def test_run_package_404(client):
    assert client.get(f"{BASE}/runs/ghost-2026-01-01-001/").status_code == 404
