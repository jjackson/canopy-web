"""Contract tests for the v2 evals Ninja surface.

Covers:
- Auth: 401 for anonymous.
- GET /{skill_id}/: auto-creates suite, returns cases+runs, 404 for bad skill.
- POST /{skill_id}/run/: returns EvalRunOut, status in expected set.
- GET /{skill_id}/history/: paginated EvalRunOut list.
- POST /{skill_id}/cases/: 201 + EvalCaseOut, 422 for empty name.
- PATCH /{skill_id}/cases/{case_id}/: partial update.
- DELETE /{skill_id}/cases/{case_id}/: 204, 404 for bogus id.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.evals.models import EvalCase, EvalRun, EvalSuite
from apps.evals.schemas import EvalCaseOut, EvalRunOut, EvalSuiteOut
from apps.skills.models import Skill

User = get_user_model()

BASE = "/api/evals"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(username="alice", email="alice@dimagi.com"):
    return User.objects.create_user(username=username, email=email, password="pw")


def _auth_client(user=None):
    c = Client()
    if user is None:
        user = _make_user()
    c.force_login(user)
    return c


def _make_skill(name="test-skill", **kwargs):
    defaults = {
        "name": name,
        "description": "A test skill",
        "definition": {"steps": []},
        "version": 1,
        "usage_count": 0,
    }
    defaults.update(kwargs)
    return Skill.objects.create(**defaults)


def _post_json(client, url, data):
    return client.post(url, json.dumps(data), content_type="application/json")


def _patch_json(client, url, data):
    return client.patch(url, json.dumps(data), content_type="application/json")


# ---------------------------------------------------------------------------
# GET /{skill_id}/ — eval suite detail
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_eval_suite_auto_creates():
    """Skill with no EvalSuite → GET creates it and returns empty suite."""
    c = _auth_client()
    skill = _make_skill("auto-create-skill")
    assert not EvalSuite.objects.filter(skill=skill).exists()

    resp = c.get(f"{BASE}/{skill.pk}/")
    assert resp.status_code == 200
    body = resp.json()
    suite = EvalSuiteOut.model_validate(body)
    assert suite.cases == []
    assert suite.runs == []
    # Side-effect: suite was created
    assert EvalSuite.objects.filter(skill=skill).exists()


@pytest.mark.django_db
def test_get_eval_suite_returns_cases_and_runs():
    """Skill with EvalSuite, 1 case, 1 run → GET returns all in EvalSuiteOut."""
    c = _auth_client()
    skill = _make_skill("full-suite-skill")
    suite = EvalSuite.objects.create(skill=skill)
    EvalCase.objects.create(
        suite=suite,
        name="Case 1",
        input_data={"q": "hello"},
        expected_output={"contains": ["world"]},
    )
    EvalRun.objects.create(
        suite=suite,
        status="completed",
        results={"cases": []},
        overall_score=0.9,
        runtime="web",
    )

    resp = c.get(f"{BASE}/{skill.pk}/")
    assert resp.status_code == 200
    body = resp.json()
    out = EvalSuiteOut.model_validate(body)
    assert len(out.cases) == 1
    assert len(out.runs) == 1
    assert out.cases[0].name == "Case 1"
    assert out.runs[0].overall_score == pytest.approx(0.9)


@pytest.mark.django_db
def test_get_eval_suite_skill_not_found():
    """Bogus skill_id → 404 + problem+json."""
    c = _auth_client()
    resp = c.get(f"{BASE}/999999/")
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("type", "").endswith("/not-found")


# ---------------------------------------------------------------------------
# POST /{skill_id}/run/ — run eval
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_run_eval():
    """POST /run/ → 200 + EvalRunOut with valid status."""
    c = _auth_client()
    skill = _make_skill("run-skill")
    suite = EvalSuite.objects.create(skill=skill)
    EvalCase.objects.create(
        suite=suite,
        name="Case A",
        input_data={"x": 1},
        expected_output={"contains": ["result"]},
    )

    # Patch EvalRunner.execute to avoid real AI calls
    fake_run = EvalRun.objects.create(
        suite=suite,
        status="completed",
        results={"cases": [{"case_id": 1, "passed": True}]},
        overall_score=1.0,
        runtime="web",
    )
    with patch("apps.evals.runner.EvalRunner.execute", return_value=fake_run):
        resp = _post_json(c, f"{BASE}/{skill.pk}/run/", {})

    assert resp.status_code in (200, 201)
    body = resp.json()
    out = EvalRunOut.model_validate(body)
    assert out.status in ("pending", "running", "completed", "failed")


# ---------------------------------------------------------------------------
# GET /{skill_id}/history/ — history paginated
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_eval_history_paginated():
    """Create 3 EvalRuns → GET history returns 3 items."""
    c = _auth_client()
    skill = _make_skill("history-skill")
    suite = EvalSuite.objects.create(skill=skill)
    for i in range(3):
        EvalRun.objects.create(
            suite=suite,
            status="completed",
            results={},
            overall_score=float(i) / 2,
            runtime="web",
        )

    resp = c.get(f"{BASE}/{skill.pk}/history/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    for item in body["items"]:
        EvalRunOut.model_validate(item)


# ---------------------------------------------------------------------------
# POST /{skill_id}/cases/ — create eval case
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_eval_case():
    """POST /cases/ → 201 + EvalCaseOut."""
    c = _auth_client()
    skill = _make_skill("case-skill")

    resp = _post_json(
        c,
        f"{BASE}/{skill.pk}/cases/",
        {
            "name": "My Case",
            "input_data": {"prompt": "hello"},
            "expected_output": {"contains": ["hi"]},
            "source_excerpt": "some excerpt",
        },
    )
    assert resp.status_code == 201
    out = EvalCaseOut.model_validate(resp.json())
    assert out.name == "My Case"
    assert out.source_excerpt == "some excerpt"


@pytest.mark.django_db
def test_create_eval_case_validates_name():
    """Empty name → 422."""
    c = _auth_client()
    skill = _make_skill("validate-name-skill")

    resp = _post_json(
        c,
        f"{BASE}/{skill.pk}/cases/",
        {
            "name": "",
            "input_data": {},
            "expected_output": {},
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /{skill_id}/cases/{case_id}/ — partial update
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_patch_eval_case_partial():
    """PATCH with only name → 200 + updated name, other fields unchanged."""
    c = _auth_client()
    skill = _make_skill("patch-skill")
    suite = EvalSuite.objects.create(skill=skill)
    case = EvalCase.objects.create(
        suite=suite,
        name="original",
        input_data={"k": "v"},
        expected_output={"contains": ["x"]},
    )

    resp = _patch_json(c, f"{BASE}/{skill.pk}/cases/{case.pk}/", {"name": "renamed"})
    assert resp.status_code == 200
    out = EvalCaseOut.model_validate(resp.json())
    assert out.name == "renamed"
    # Other fields preserved
    assert out.input_data == {"k": "v"}


# ---------------------------------------------------------------------------
# DELETE /{skill_id}/cases/{case_id}/ — delete eval case
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_eval_case():
    """DELETE → 204 no body."""
    c = _auth_client()
    skill = _make_skill("delete-skill")
    suite = EvalSuite.objects.create(skill=skill)
    case = EvalCase.objects.create(
        suite=suite,
        name="to-delete",
        input_data={},
        expected_output={},
    )

    resp = c.delete(f"{BASE}/{skill.pk}/cases/{case.pk}/")
    assert resp.status_code == 204
    assert not EvalCase.objects.filter(pk=case.pk).exists()


@pytest.mark.django_db
def test_delete_eval_case_404():
    """Bogus case_id → 404 + problem+json."""
    c = _auth_client()
    skill = _make_skill("delete-404-skill")

    resp = c.delete(f"{BASE}/{skill.pk}/cases/999999/")
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("type", "").endswith("/not-found")


# ---------------------------------------------------------------------------
# Auth: anonymous → 401
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_anonymous_401():
    """Anonymous request → 401 + problem+json."""
    skill = _make_skill("anon-skill")
    anon = Client()
    resp = anon.get(f"{BASE}/{skill.pk}/")
    assert resp.status_code == 401
    body = resp.json()
    assert body.get("type", "").endswith("/auth")
