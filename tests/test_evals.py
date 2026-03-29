import json
from unittest.mock import patch

import pytest
from django.test import Client

from apps.evals.models import EvalCase, EvalRun, EvalSuite
from apps.evals.runner import EvalRunner, check_expected
from apps.skills.models import Skill

SAMPLE_SKILL_DEF = {
    "name": "test-skill",
    "steps": [
        {"name": "analyze", "description": "Analyze the input data"},
        {"name": "synthesize", "description": "Produce a summary"},
    ],
}


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def skill(db):
    return Skill.objects.create(
        name="test-skill",
        description="A skill for testing evals",
        definition=SAMPLE_SKILL_DEF,
    )


@pytest.fixture
def eval_suite(skill):
    return EvalSuite.objects.create(skill=skill)


@pytest.fixture
def eval_case(eval_suite):
    return EvalCase.objects.create(
        suite=eval_suite,
        name="basic-case",
        input_data={"topic": "climate change"},
        expected_output={"contains": ["climate", "temperature"]},
    )


class TestCheckExpectedContains:
    """Unit tests for the check_expected function."""

    def test_all_terms_present(self):
        output = "Climate change affects global temperature patterns."
        expected = {"contains": ["climate", "temperature"]}
        passed, reasons = check_expected(output, expected)
        assert passed is True
        assert reasons == []

    def test_missing_term(self):
        output = "The weather is nice today."
        expected = {"contains": ["climate", "temperature"]}
        passed, reasons = check_expected(output, expected)
        assert passed is False
        assert len(reasons) == 2
        assert "Missing expected term: 'climate'" in reasons
        assert "Missing expected term: 'temperature'" in reasons

    def test_case_insensitive_match(self):
        output = "CLIMATE and TEMPERATURE are related."
        expected = {"contains": ["climate", "temperature"]}
        passed, reasons = check_expected(output, expected)
        assert passed is True
        assert reasons == []

    def test_empty_contains(self):
        output = "Any text here."
        expected = {"contains": []}
        passed, reasons = check_expected(output, expected)
        assert passed is True
        assert reasons == []

    def test_empty_expected(self):
        output = "Any text here."
        expected = {}
        passed, reasons = check_expected(output, expected)
        assert passed is True
        assert reasons == []

    def test_partial_match(self):
        output = "Climate is important."
        expected = {"contains": ["climate", "temperature"]}
        passed, reasons = check_expected(output, expected)
        assert passed is False
        assert len(reasons) == 1
        assert "Missing expected term: 'temperature'" in reasons


class TestRunEvalAllPass:
    """Test that all cases pass when mock returns expected terms."""

    @patch("apps.evals.runner.run_skill_step")
    def test_run_eval_all_pass(self, mock_run_step, skill, eval_suite, eval_case):
        mock_run_step.return_value = "Analysis of climate change shows rising temperature globally."

        runner = EvalRunner(skill)
        run = runner.execute(eval_suite)

        assert run.status == "completed"
        assert run.overall_score == 1.0
        assert len(run.results["cases"]) == 1
        assert run.results["cases"][0]["passed"] is True
        assert run.results["cases"][0]["reasons"] == []

        # Verify usage_count incremented
        skill.refresh_from_db()
        assert skill.usage_count == 1


class TestRunEvalPartialFail:
    """Test partial failure when mock returns text missing expected terms."""

    @patch("apps.evals.runner.run_skill_step")
    def test_run_eval_partial_fail(self, mock_run_step, skill, eval_suite):
        # Create two cases
        EvalCase.objects.create(
            suite=eval_suite,
            name="case-pass",
            input_data={"topic": "climate"},
            expected_output={"contains": ["climate"]},
        )
        EvalCase.objects.create(
            suite=eval_suite,
            name="case-fail",
            input_data={"topic": "energy"},
            expected_output={"contains": ["solar", "renewable"]},
        )

        # Mock returns text that has climate but not solar/renewable
        mock_run_step.return_value = "Climate change is a serious issue."

        runner = EvalRunner(skill)
        run = runner.execute(eval_suite)

        assert run.status == "completed"
        assert run.overall_score == 0.5
        assert len(run.results["cases"]) == 2

        results_by_name = {r["case_name"]: r for r in run.results["cases"]}
        assert results_by_name["case-pass"]["passed"] is True
        assert results_by_name["case-fail"]["passed"] is False
        assert len(results_by_name["case-fail"]["reasons"]) == 2


class TestEvalSuiteAPI:
    """Test GET /api/evals/{skill_id}/ returns suite."""

    def test_eval_suite_api(self, client, skill, eval_suite, eval_case):
        response = client.get(f"/api/evals/{skill.pk}/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]["cases"]) == 1
        assert body["data"]["cases"][0]["name"] == "basic-case"

    def test_eval_suite_auto_creates(self, client, skill):
        """Suite is auto-created if it doesn't exist."""
        response = client.get(f"/api/evals/{skill.pk}/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["cases"] == []

    def test_eval_suite_skill_not_found(self, client, db):
        response = client.get("/api/evals/9999/")
        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False


class TestRunEvalAPI:
    """Test POST /api/evals/{skill_id}/run/ (mocked) returns results."""

    @patch("apps.evals.views.EvalRunner")
    def test_run_eval_api(self, MockRunner, client, skill, eval_suite, eval_case):
        mock_run = EvalRun.objects.create(
            suite=eval_suite,
            status="completed",
            results={"cases": [{"case_id": eval_case.pk, "case_name": "basic-case", "passed": True, "reasons": []}]},
            overall_score=1.0,
            runtime="0.5s",
        )
        mock_runner_instance = MockRunner.return_value
        mock_runner_instance.execute.return_value = mock_run

        response = client.post(f"/api/evals/{skill.pk}/run/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "completed"
        assert body["data"]["overall_score"] == 1.0

    def test_run_eval_no_cases(self, client, skill, eval_suite):
        """Should return error if suite has no cases."""
        response = client.post(f"/api/evals/{skill.pk}/run/")
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False

    def test_run_eval_skill_not_found(self, client, db):
        response = client.post("/api/evals/9999/run/")
        assert response.status_code == 404


class TestProposeEvalCase:
    """Test POST /api/evals/{skill_id}/cases/ adds a new case."""

    def test_propose_eval_case(self, client, skill):
        payload = {
            "name": "new-case",
            "input_data": {"query": "What is photosynthesis?"},
            "expected_output": {"contains": ["sunlight", "chlorophyll"]},
            "source_excerpt": "Biology textbook chapter 5",
        }
        response = client.post(
            f"/api/evals/{skill.pk}/cases/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["name"] == "new-case"
        assert body["data"]["input_data"] == {"query": "What is photosynthesis?"}
        assert body["data"]["expected_output"] == {"contains": ["sunlight", "chlorophyll"]}
        assert body["data"]["source_excerpt"] == "Biology textbook chapter 5"

        # Verify case was persisted
        assert EvalCase.objects.filter(name="new-case").exists()

    def test_propose_eval_case_without_excerpt(self, client, skill):
        payload = {
            "name": "minimal-case",
            "input_data": {"query": "test"},
            "expected_output": {"contains": ["result"]},
        }
        response = client.post(
            f"/api/evals/{skill.pk}/cases/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["source_excerpt"] == ""

    def test_propose_eval_case_missing_fields(self, client, skill):
        payload = {"name": "incomplete-case"}
        response = client.post(
            f"/api/evals/{skill.pk}/cases/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False

    def test_propose_eval_case_skill_not_found(self, client, db):
        payload = {
            "name": "orphan-case",
            "input_data": {},
            "expected_output": {"contains": []},
        }
        response = client.post(
            "/api/evals/9999/cases/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 404


class TestEvalHistory:
    """Test GET /api/evals/{skill_id}/history/ returns runs."""

    def test_eval_history(self, client, skill, eval_suite):
        # Create multiple runs
        EvalRun.objects.create(
            suite=eval_suite,
            status="completed",
            results={"cases": []},
            overall_score=0.8,
            runtime="1.2s",
        )
        EvalRun.objects.create(
            suite=eval_suite,
            status="completed",
            results={"cases": []},
            overall_score=0.9,
            runtime="0.9s",
        )

        response = client.get(f"/api/evals/{skill.pk}/history/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) == 2
        # Most recent first
        assert body["data"][0]["overall_score"] == 0.9

    def test_eval_history_empty(self, client, skill):
        response = client.get(f"/api/evals/{skill.pk}/history/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    def test_eval_history_skill_not_found(self, client, db):
        response = client.get("/api/evals/9999/history/")
        assert response.status_code == 404
