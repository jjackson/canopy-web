"""Contract tests for the v2 workspace Ninja surface.

Covers:
- GET  /            : list sessions (2 rows), filter by status.
- GET  /{id}/       : 200 + WorkspaceSessionOut, 404 + problem+json.
- PATCH /{id}/edit/ : updates skill_draft + appends to edit_history.
- POST /{id}/publish/: creates Skill, EvalSuite, EvalCase (201).
- POST /start/{collection_id}/ : SSE stream (monkeypatched).
- POST /analyze/{collection_id}/: synchronous JSON 201 (monkeypatched call_ai).
- Anonymous → 401 for SSE and non-SSE endpoints.
"""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.collections.models import Collection, Source
from apps.evals.models import EvalCase, EvalSuite
from apps.skills.models import Skill
from apps.workspace.models import WorkspaceSession
from apps.workspace.schemas import WorkspaceSessionListItemOut, WorkspaceSessionOut

User = get_user_model()

BASE = "/api/v2/workspace"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(username="alice", email="alice@dimagi.com"):
    return User.objects.create_user(username=username, email=email, password="pw")


# ---------------------------------------------------------------------------
# Fixtures (used by the synchronous /analyze/ tests)
# ---------------------------------------------------------------------------


@pytest.fixture()
def authed_client():
    """Authenticated Django test client."""
    c = Client()
    c.force_login(_make_user(username="fixture_user", email="fixture@dimagi.com"))
    return c


@pytest.fixture()
def collection():
    """A collection with NO sources (triggers empty-collection 400 by default)."""
    return _make_collection("Fixture Collection", with_source=False)


def _auth_client(user=None):
    c = Client()
    if user is None:
        user = _make_user()
    c.force_login(user)
    return c


def _post_json(client, url, data):
    return client.post(url, json.dumps(data), content_type="application/json")


def _patch_json(client, url, data):
    return client.patch(url, json.dumps(data), content_type="application/json")


def _make_collection(name="Test Collection", with_source=False):
    col = Collection.objects.create(name=name, description="desc")
    if with_source:
        Source.objects.create(
            collection=col,
            source_type="slack",
            title="Sample",
            content="Sample source content for analysis.",
        )
    return col


def _make_session(collection=None, **kwargs):
    if collection is None:
        collection = _make_collection()
    defaults = {"status": "proposed", "proposed_approach": {"name": "skill-x"}}
    defaults.update(kwargs)
    return WorkspaceSession.objects.create(collection=collection, **defaults)


# ---------------------------------------------------------------------------
# GET / — list sessions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_sessions():
    """Create 2 sessions; list returns both items."""
    c = _auth_client()
    col = _make_collection("List Col")
    _make_session(col, status="proposed")
    _make_session(col, status="editing")

    resp = c.get(f"{BASE}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    # Each item is valid
    for item in body["items"]:
        WorkspaceSessionListItemOut.model_validate(item)


@pytest.mark.django_db
def test_list_sessions_filter_by_status():
    """?status=proposed returns only proposed sessions."""
    c = _auth_client()
    col = _make_collection("Filter Col")
    _make_session(col, status="proposed")
    _make_session(col, status="editing")
    _make_session(col, status="published")

    resp = c.get(f"{BASE}/?status=proposed")
    assert resp.status_code == 200
    body = resp.json()
    assert all(item["status"] == "proposed" for item in body["items"])
    # Exactly our one proposed session is returned
    assert body["total"] >= 1
    assert not any(item["status"] == "editing" for item in body["items"])


# ---------------------------------------------------------------------------
# GET /{session_id}/ — session detail
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_session_detail():
    """GET /{id}/ returns 200 + valid WorkspaceSessionOut."""
    c = _auth_client()
    session = _make_session()

    resp = c.get(f"{BASE}/{session.pk}/")
    assert resp.status_code == 200
    out = WorkspaceSessionOut.model_validate(resp.json())
    assert out.id == session.pk
    assert out.status == session.status


@pytest.mark.django_db
def test_get_session_404():
    """Bogus session id → 404 + problem+json."""
    c = _auth_client()
    resp = c.get(f"{BASE}/999999/")
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("type", "").endswith("/not-found")


# ---------------------------------------------------------------------------
# PATCH /{session_id}/edit/ — edit skill draft
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_edit_skill_appends_to_history():
    """PATCH /edit/ updates skill_draft and adds an entry to edit_history."""
    c = _auth_client()
    session = _make_session(skill_draft={"name": "old"}, edit_history=[])

    new_draft = {"name": "new-name", "description": "updated"}
    resp = _patch_json(c, f"{BASE}/{session.pk}/edit/", {"skill_draft": new_draft})

    assert resp.status_code == 200
    out = WorkspaceSessionOut.model_validate(resp.json())
    assert out.skill_draft == new_draft
    assert len(out.edit_history) == 1  # one entry appended

    # Verify DB state
    session.refresh_from_db()
    assert session.skill_draft == new_draft
    assert len(session.edit_history) == 1


@pytest.mark.django_db
def test_edit_skill_note_stored_in_history():
    """PATCH /edit/ with a note stores it in the edit_history entry."""
    c = _auth_client()
    session = _make_session()

    resp = _patch_json(
        c,
        f"{BASE}/{session.pk}/edit/",
        {"skill_draft": {"name": "x"}, "note": "My edit note"},
    )
    assert resp.status_code == 200
    out = WorkspaceSessionOut.model_validate(resp.json())
    assert len(out.edit_history) == 1
    assert out.edit_history[0].get("note") == "My edit note"


# ---------------------------------------------------------------------------
# POST /{session_id}/publish/ — publish skill
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_publish_skill_creates_skill_eval_suite_and_cases():
    """POST /publish/ creates Skill, EvalSuite, and one EvalCase per proposed case."""
    c = _auth_client()
    session = _make_session(
        status="proposed",
        proposed_approach={"name": "my-skill", "description": "does X"},
        proposed_eval_cases=[{"name": "case1", "input": {"q": "hello"}, "expected": {"r": "world"}}],
        skill_draft={"name": "my-skill"},
    )

    resp = _post_json(c, f"{BASE}/{session.pk}/publish/", {})
    assert resp.status_code == 201

    # Skill was created
    skill = Skill.objects.filter(name="my-skill").first()
    assert skill is not None

    # EvalSuite was created
    assert EvalSuite.objects.filter(skill=skill).exists()
    suite = EvalSuite.objects.get(skill=skill)

    # EvalCase was created
    assert EvalCase.objects.filter(suite=suite).count() == 1
    case = EvalCase.objects.get(suite=suite)
    assert case.name == "case1"

    # Session marked published
    session.refresh_from_db()
    assert session.status == "published"


@pytest.mark.django_db
def test_publish_skill_name_override():
    """POST /publish/ with a name payload overrides the approach name."""
    c = _auth_client()
    session = _make_session(
        status="proposed",
        proposed_approach={"name": "original-name", "description": "desc"},
        proposed_eval_cases=[],
        skill_draft={},
    )

    resp = _post_json(c, f"{BASE}/{session.pk}/publish/", {"name": "override-name"})
    assert resp.status_code == 201
    assert Skill.objects.filter(name="override-name").exists()


# ---------------------------------------------------------------------------
# POST /start/{collection_id}/ — SSE stream
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_start_workspace_returns_event_stream(monkeypatch):
    """POST /start/ returns text/event-stream; stream contains start + done events."""
    c = _auth_client()
    col = _make_collection("SSE Start Col", with_source=True)

    def fake_stream(*args, **kwargs):
        yield b"event: start\ndata: {}\n\n"
        yield b"event: done\ndata: {}\n\n"

    monkeypatch.setattr("apps.workspace.api.stream_workspace_analysis", fake_stream)

    resp = c.post(f"{BASE}/start/{col.pk}/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/event-stream")
    body = b"".join(resp.streaming_content)
    assert b"event: start" in body
    assert b"event: done" in body


@pytest.mark.django_db
def test_start_workspace_404_unknown_collection(monkeypatch):
    """POST /start/ with unknown collection id → 404."""
    c = _auth_client()

    def fake_stream(*args, **kwargs):
        yield b""

    monkeypatch.setattr("apps.workspace.api.stream_workspace_analysis", fake_stream)
    resp = c.post(f"{BASE}/start/999999/")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /analyze/{collection_id}/ — synchronous JSON (DRF parity)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_analyze_workspace_returns_json_proposal(authed_client, collection, monkeypatch):
    """Sync analysis — returns 201 + parsed proposal, NOT an SSE stream."""

    def fake_call_ai(system, prompt):
        return '{"approach": {"name": "x"}, "eval_cases": [{"name": "case1"}]}'

    # Give the collection a source so build_analysis_prompt() doesn't raise.
    Source.objects.create(
        collection=collection,
        source_type="slack",
        title="Sample",
        content="Sample source content for analysis.",
    )

    monkeypatch.setattr("apps.workspace.api.call_ai", fake_call_ai)
    response = authed_client.post(f"{BASE}/analyze/{collection.pk}/")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "proposed"
    assert body["approach"]["name"] == "x"
    assert len(body["eval_cases"]) == 1
    assert body["session_id"] >= 1


@pytest.mark.django_db
def test_analyze_workspace_empty_collection_400(authed_client, collection):
    """Empty collection (no sources) → 400 problem+json."""
    response = authed_client.post(f"{BASE}/analyze/{collection.pk}/")
    # The collection fixture has no sources, so build_analysis_prompt raises ValueError
    assert response.status_code == 400
    body = response.json()
    assert body["type"].endswith("/validation")


@pytest.mark.django_db
def test_analyze_workspace_404_unknown_collection():
    """POST /analyze/ with unknown collection id → 404."""
    c = _auth_client()
    resp = c.post(f"{BASE}/analyze/999999/")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth: anonymous → 401
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_anonymous_401_list():
    """Anonymous GET / → 401 + problem+json."""
    anon = Client()
    resp = anon.get(f"{BASE}/")
    assert resp.status_code == 401
    assert resp.json().get("type", "").endswith("/auth")


@pytest.mark.django_db
def test_anonymous_401_sse(monkeypatch):
    """Anonymous POST /start/ → 401 + problem+json (SSE endpoint)."""
    col = _make_collection("Anon SSE Col")

    def fake_stream(*args, **kwargs):
        yield b""

    monkeypatch.setattr("apps.workspace.api.stream_workspace_analysis", fake_stream)

    anon = Client()
    resp = anon.post(f"{BASE}/start/{col.pk}/")
    assert resp.status_code == 401
    assert resp.json().get("type", "").endswith("/auth")
