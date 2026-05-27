import pytest

from apps.evals.schemas import (
    EvalCaseCreateIn,
    EvalCasePatchIn,
    EvalRunOut,
    EvalSuiteOut,
)


def test_eval_suite_round_trip():
    raw = {
        "id": 1,
        "cases": [
            {
                "id": 10,
                "name": "happy path",
                "input_data": {"prompt": "x"},
                "expected_output": {"text": "y"},
                "source_excerpt": "from session 3",
                "created_at": "2026-05-20T10:00:00Z",
            }
        ],
        "runs": [
            {
                "id": 100,
                "status": "completed",
                "results": {"pass": 5, "fail": 0},
                "overall_score": 1.0,
                "runtime": "web",
                "created_at": "2026-05-21T10:00:00Z",
            }
        ],
        "created_at": "2026-05-20T10:00:00Z",
    }
    parsed = EvalSuiteOut.model_validate(raw)
    assert parsed.cases[0].name == "happy path"
    assert parsed.runs[0].overall_score == 1.0


def test_eval_case_create_validation():
    with pytest.raises(ValueError):
        EvalCaseCreateIn(name="", input_data={}, expected_output={})
    obj = EvalCaseCreateIn(name="x", input_data={}, expected_output={})
    assert obj.name == "x"


def test_eval_case_patch_partial():
    obj = EvalCasePatchIn(name="renamed")
    dumped = obj.model_dump(exclude_unset=True)
    assert dumped == {"name": "renamed"}


def test_eval_run_status_literal():
    obj = EvalRunOut.model_validate({
        "id": 1,
        "status": "running",
        "results": {},
        "overall_score": None,
        "runtime": "claude_code",
        "created_at": "2026-05-21T10:00:00Z",
    })
    assert obj.status == "running"
