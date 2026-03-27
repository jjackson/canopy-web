import json

import pytest
from django.test import Client

from apps.skills.models import Skill

SAMPLE_SKILL = {
    "name": "crispr-analysis",
    "description": "Analyze CRISPR data using evidence synthesis",
    "steps": [
        {
            "name": "gather_evidence",
            "description": "Collect relevant studies",
            "tools": ["web_search"],
            "inputs": ["topic"],
            "outputs": ["evidence_set"],
        },
        {
            "name": "synthesize",
            "description": "Produce analysis",
            "tools": ["llm_reasoning"],
            "inputs": ["evidence_set"],
            "outputs": ["draft"],
        },
        {
            "name": "review",
            "description": "Adversarial review",
            "tools": ["llm_reasoning"],
            "inputs": ["draft"],
            "outputs": ["final"],
        },
    ],
}


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def skill(db):
    return Skill.objects.create(
        name="crispr-analysis",
        description="Analyze CRISPR data using evidence synthesis",
        definition=SAMPLE_SKILL,
    )


class TestSkillList:
    def test_list_skills(self, client, skill):
        response = client.get("/api/skills/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) == 1
        assert body["data"][0]["name"] == "crispr-analysis"

    def test_list_skills_empty(self, client, db):
        response = client.get("/api/skills/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    def test_list_skills_with_sort(self, client, db):
        Skill.objects.create(name="beta-skill", definition={})
        Skill.objects.create(name="alpha-skill", definition={})
        response = client.get("/api/skills/?sort=name")
        assert response.status_code == 200
        body = response.json()
        names = [s["name"] for s in body["data"]]
        assert names == ["alpha-skill", "beta-skill"]


class TestSkillDetail:
    def test_get_skill(self, client, skill):
        response = client.get(f"/api/skills/{skill.pk}/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["name"] == "crispr-analysis"
        assert body["data"]["definition"] == SAMPLE_SKILL
        assert "eval_score" in body["data"]

    def test_get_skill_not_found(self, client, db):
        response = client.get("/api/skills/9999/")
        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False


class TestGenerateAdapter:
    def test_generate_web_adapter(self, client, skill):
        response = client.post(
            f"/api/skills/{skill.pk}/adapter/",
            data=json.dumps({"runtime": "web"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["type"] == "guided_workflow"
        assert len(body["data"]["ui_steps"]) == 3

    def test_generate_claude_code_adapter(self, client, skill):
        response = client.post(
            f"/api/skills/{skill.pk}/adapter/",
            data=json.dumps({"runtime": "claude_code"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["type"] == "skill"
        assert "crispr-analysis" in body["data"]["content"]

    def test_generate_open_claw_adapter(self, client, skill):
        response = client.post(
            f"/api/skills/{skill.pk}/adapter/",
            data=json.dumps({"runtime": "open_claw"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["type"] == "prompt_chain"

    def test_unknown_runtime_returns_error(self, client, skill):
        response = client.post(
            f"/api/skills/{skill.pk}/adapter/",
            data=json.dumps({"runtime": "unknown"}),
            content_type="application/json",
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False

    def test_missing_runtime_returns_error(self, client, skill):
        response = client.post(
            f"/api/skills/{skill.pk}/adapter/",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False

    def test_adapter_skill_not_found(self, client, db):
        response = client.post(
            "/api/skills/9999/adapter/",
            data=json.dumps({"runtime": "web"}),
            content_type="application/json",
        )
        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False
