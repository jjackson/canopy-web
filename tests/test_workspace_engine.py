"""
Tests for the workspace engine.

Tests engine logic (prompt building, response parsing) and the publish
endpoint. Does NOT test streaming or actual LLM calls.
"""
import json

import pytest
from django.test import Client

from apps.collections.models import Collection, Source
from apps.evals.models import EvalCase, EvalSuite
from apps.skills.models import Skill
from apps.workspace.engine import WorkspaceEngine
from apps.workspace.models import WorkspaceSession


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def collection(db):
    return Collection.objects.create(
        name="Test Collection",
        description="A test collection",
    )


@pytest.fixture
def collection_with_sources(collection):
    Source.objects.create(
        collection=collection,
        source_type="slack",
        title="Slack Thread 1",
        content="User asked how to deploy. Bot explained the steps.",
    )
    Source.objects.create(
        collection=collection,
        source_type="transcript",
        title="Session Transcript",
        content="AI helped user write a deployment script with error handling.",
    )
    return collection


@pytest.fixture
def engine(collection_with_sources):
    return WorkspaceEngine(collection_with_sources)


@pytest.fixture
def empty_engine(collection):
    return WorkspaceEngine(collection)


@pytest.fixture
def session_with_proposal(collection_with_sources):
    return WorkspaceSession.objects.create(
        collection=collection_with_sources,
        status="proposed",
        proposed_approach={
            "name": "Deployment Helper",
            "description": "Helps deploy applications",
            "steps": [
                {
                    "name": "Check environment",
                    "description": "Verify deployment prerequisites",
                    "tools": ["shell"],
                    "inputs": ["env_name"],
                    "outputs": ["env_status"],
                }
            ],
        },
        proposed_eval_cases=[
            {
                "name": "Basic deploy",
                "input": {"env_name": "staging"},
                "expected": {"status": "success"},
            },
            {
                "name": "Missing env",
                "input": {"env_name": ""},
                "expected": {"status": "error"},
            },
        ],
    )


class TestCreateSession:
    def test_start_session_creates_workspace(self, engine):
        session = engine.create_session()
        assert isinstance(session, WorkspaceSession)
        assert session.pk is not None
        assert session.status == "created"
        assert session.collection == engine.collection
        assert WorkspaceSession.objects.filter(pk=session.pk).exists()


class TestBuildAnalysisPrompt:
    def test_build_analysis_prompt_includes_all_sources(self, engine):
        prompt = engine.build_analysis_prompt()
        assert "Slack Thread 1" in prompt
        assert "User asked how to deploy" in prompt
        assert "Session Transcript" in prompt
        assert "AI helped user write a deployment script" in prompt

    def test_empty_collection_raises(self, empty_engine):
        with pytest.raises(ValueError, match="no sources"):
            empty_engine.build_analysis_prompt()


class TestParseAiResponse:
    def test_parse_approach_response(self):
        raw = json.dumps({
            "approach": {
                "name": "Test Skill",
                "description": "A test skill",
                "steps": [],
            },
            "eval_cases": [
                {"name": "case1", "input": {}, "expected": {}},
            ],
        })
        result = WorkspaceEngine.parse_ai_response(raw)
        assert "approach" in result
        assert result["approach"]["name"] == "Test Skill"
        assert len(result["eval_cases"]) == 1

    def test_parse_with_markdown_fences(self):
        raw = '```json\n{"approach": {"name": "Fenced"}, "eval_cases": []}\n```'
        result = WorkspaceEngine.parse_ai_response(raw)
        assert result["approach"]["name"] == "Fenced"

    def test_parse_with_plain_fences(self):
        raw = '```\n{"approach": {"name": "Plain"}, "eval_cases": []}\n```'
        result = WorkspaceEngine.parse_ai_response(raw)
        assert result["approach"]["name"] == "Plain"

    def test_parse_malformed_response_raises(self):
        with pytest.raises(ValueError, match="Failed to parse"):
            WorkspaceEngine.parse_ai_response("this is not json")

    def test_parse_missing_approach_raises(self):
        raw = json.dumps({"eval_cases": []})
        with pytest.raises(ValueError, match="missing required 'approach' key"):
            WorkspaceEngine.parse_ai_response(raw)

    def test_parse_non_object_raises(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            WorkspaceEngine.parse_ai_response('"just a string"')


class TestBuildReProposalPrompt:
    def test_build_re_proposal_prompt(self, engine):
        current_skill = {"approach": {"name": "Old"}, "eval_cases": []}
        user_edit = {"name": "New Name"}
        prompt = engine.build_re_proposal_prompt(current_skill, user_edit)
        assert "Old" in prompt
        assert "New Name" in prompt


class TestPublishSkill:
    def test_publish_creates_skill_and_eval(self, client, session_with_proposal):
        response = client.post(
            f"/api/workspace/{session_with_proposal.pk}/publish/",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["name"] == "Deployment Helper"
        assert body["data"]["eval_count"] == 2

        # Verify the skill was created
        skill = Skill.objects.get(pk=body["data"]["skill_id"])
        assert skill.name == "Deployment Helper"
        assert skill.description == "Helps deploy applications"
        assert skill.definition["name"] == "Deployment Helper"
        assert skill.workspace_session == session_with_proposal

        # Verify eval suite and cases
        eval_suite = EvalSuite.objects.get(skill=skill)
        cases = EvalCase.objects.filter(suite=eval_suite)
        assert cases.count() == 2
        case_names = set(cases.values_list("name", flat=True))
        assert case_names == {"Basic deploy", "Missing env"}

        # Verify session status updated
        session_with_proposal.refresh_from_db()
        assert session_with_proposal.status == "published"

    def test_publish_no_proposal_returns_error(self, client, db):
        collection = Collection.objects.create(name="Empty")
        session = WorkspaceSession.objects.create(collection=collection)
        response = client.post(f"/api/workspace/{session.pk}/publish/")
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "NO_PROPOSAL"

    def test_publish_session_not_found(self, client, db):
        response = client.post("/api/workspace/9999/publish/")
        assert response.status_code == 404


class TestWorkspaceDetail:
    def test_get_session_detail(self, client, session_with_proposal):
        response = client.get(f"/api/workspace/{session_with_proposal.pk}/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["id"] == session_with_proposal.pk
        assert body["data"]["status"] == "proposed"
        assert body["data"]["proposed_approach"]["name"] == "Deployment Helper"
        assert len(body["data"]["proposed_eval_cases"]) == 2

    def test_get_session_not_found(self, client, db):
        response = client.get("/api/workspace/9999/")
        assert response.status_code == 404


class TestEditSkill:
    def test_non_structural_edit(self, client, session_with_proposal):
        response = client.patch(
            f"/api/workspace/{session_with_proposal.pk}/edit/",
            data=json.dumps({
                "edit": {"description": "Updated description"},
                "structural": False,
            }),
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "editing"
        assert body["data"]["proposed_approach"]["description"] == "Updated description"

    def test_edit_session_not_found(self, client, db):
        response = client.patch(
            "/api/workspace/9999/edit/",
            data=json.dumps({"edit": {}, "structural": False}),
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_edit_invalid_json(self, client, session_with_proposal):
        response = client.patch(
            f"/api/workspace/{session_with_proposal.pk}/edit/",
            data="not json",
            content_type="application/json",
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "INVALID_JSON"
