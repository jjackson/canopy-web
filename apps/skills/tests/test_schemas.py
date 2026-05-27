import pytest

from apps.skills.schemas import (
    AdapterIn,
    SkillOut,
)


def test_skill_out_round_trip():
    raw = {
        "id": 1,
        "name": "discovery-call-debrief",
        "description": "Summarize a discovery call.",
        "definition": {"prompt": "...", "evals": []},
        "version": 3,
        "usage_count": 17,
        "eval_score": 0.82,
        "eval_trend": "improving",
        "last_eval_at": "2026-05-24T18:00:00Z",
        "created_at": "2026-04-12T10:00:00Z",
        "updated_at": "2026-05-24T18:00:00Z",
    }
    parsed = SkillOut.model_validate(raw)
    assert parsed.eval_trend == "improving"


def test_skill_out_null_evals():
    raw = {
        "id": 1,
        "name": "x",
        "description": "",
        "definition": {},
        "version": 1,
        "usage_count": 0,
        "eval_score": None,
        "eval_trend": None,
        "last_eval_at": None,
        "created_at": "2026-04-12T10:00:00Z",
        "updated_at": "2026-04-12T10:00:00Z",
    }
    parsed = SkillOut.model_validate(raw)
    assert parsed.eval_score is None


def test_adapter_in_validates_runtime():
    obj = AdapterIn(runtime="web")
    assert obj.runtime == "web"
    with pytest.raises(ValueError):
        AdapterIn(runtime="bogus")


def test_eval_trend_literal():
    obj = SkillOut.model_validate({
        "id": 1, "name": "x", "description": "", "definition": {},
        "version": 1, "usage_count": 0, "eval_score": None,
        "eval_trend": "declining", "last_eval_at": None,
        "created_at": "2026-04-12T10:00:00Z",
        "updated_at": "2026-04-12T10:00:00Z",
    })
    assert obj.eval_trend == "declining"
