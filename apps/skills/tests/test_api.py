"""Contract tests for the v2 skills Ninja surface.

Covers:
- Auth: 401 for anonymous.
- List: items round-trip through SkillOut, total correct.
- Eval fields: populated when EvalRun exists, None when no suite.
- Detail: 200 + SkillOut, 404 + problem+json.
- Adapter: 200 + AdapterOut, 422 for invalid runtime.
"""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.evals.models import EvalRun, EvalSuite
from apps.skills.models import Skill
from apps.skills.schemas import AdapterOut, SkillOut

User = get_user_model()

BASE = "/api/v2/skills"


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


def _post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type="application/json")


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


# ---------------------------------------------------------------------------
# List skills
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_skills_returns_pydantic_validated_payload():
    user = _make_user()
    c = _auth_client(user)
    _make_skill("skill-one")
    _make_skill("skill-two")
    resp = c.get(f"{BASE}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    for item in body["items"]:
        SkillOut.model_validate(item)


@pytest.mark.django_db
def test_list_skills_eval_score_populated():
    user = _make_user()
    c = _auth_client(user)
    skill = _make_skill("scored-skill")
    suite = EvalSuite.objects.create(skill=skill)
    EvalRun.objects.create(suite=suite, status="completed", overall_score=0.85)

    resp = c.get(f"{BASE}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["eval_score"] == pytest.approx(0.85)


@pytest.mark.django_db
def test_list_skills_null_evals_when_no_runs():
    user = _make_user()
    c = _auth_client(user)
    _make_skill("bare-skill")  # No EvalSuite at all

    resp = c.get(f"{BASE}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["eval_score"] is None
    assert item["eval_trend"] is None
    assert item["last_eval_at"] is None


# ---------------------------------------------------------------------------
# Skill detail
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_skill_detail():
    user = _make_user()
    c = _auth_client(user)
    skill = _make_skill("detail-skill")

    resp = c.get(f"{BASE}/{skill.pk}/")
    assert resp.status_code == 200
    SkillOut.model_validate(resp.json())


@pytest.mark.django_db
def test_get_skill_404():
    c = _auth_client()
    resp = c.get(f"{BASE}/999999/")
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("type", "").endswith("/not-found")


# ---------------------------------------------------------------------------
# Generate adapter
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_generate_adapter():
    user = _make_user()
    c = _auth_client(user)
    skill = _make_skill("adapter-skill", definition={"steps": [{"name": "step1"}]})

    resp = _post_json(c, f"{BASE}/{skill.pk}/adapter/", {"runtime": "web"})
    assert resp.status_code == 200
    out = AdapterOut.model_validate(resp.json())
    assert out.runtime == "web"
    assert isinstance(out.content, str) and len(out.content) > 0


@pytest.mark.django_db
def test_generate_adapter_invalid_runtime():
    user = _make_user()
    c = _auth_client(user)
    skill = _make_skill("adapter-skill-2")

    resp = _post_json(c, f"{BASE}/{skill.pk}/adapter/", {"runtime": "bogus"})
    assert resp.status_code == 422
    body = resp.json()
    assert "type" in body


# ---------------------------------------------------------------------------
# Auth: anonymous → 401
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_anonymous_401():
    skill = _make_skill("anon-skill")
    anon = Client()
    resp = anon.get(f"{BASE}/{skill.pk}/")
    assert resp.status_code == 401
    body = resp.json()
    assert body.get("type", "").endswith("/auth")
