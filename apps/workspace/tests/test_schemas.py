import pytest

from apps.workspace.schemas import (
    EditSkillIn,
    PublishSkillIn,
    WorkspaceSessionListItemOut,
    WorkspaceSessionOut,
)


def test_workspace_session_list_item():
    raw = {
        "id": 1,
        "collection_id": 5,
        "collection_name": "Discovery call — ACME",
        "status": "proposed",
        "skill_name": "discovery-debrief",
        "created_at": "2026-05-20T10:00:00Z",
        "updated_at": "2026-05-20T10:05:00Z",
    }
    parsed = WorkspaceSessionListItemOut.model_validate(raw)
    assert parsed.status == "proposed"
    assert parsed.skill_name == "discovery-debrief"


def test_workspace_session_list_item_null_skill_name():
    raw = {
        "id": 1,
        "collection_id": 5,
        "collection_name": "X",
        "status": "created",
        "skill_name": None,
        "created_at": "2026-05-20T10:00:00Z",
        "updated_at": "2026-05-20T10:00:00Z",
    }
    parsed = WorkspaceSessionListItemOut.model_validate(raw)
    assert parsed.skill_name is None


def test_workspace_session_out_round_trip():
    raw = {
        "id": 1,
        "collection_id": 5,
        "status": "editing",
        "proposed_approach": {"name": "x", "description": "y"},
        "proposed_eval_cases": [{"name": "case1"}],
        "skill_draft": {"prompt": "..."},
        "edit_history": [{"timestamp": "2026-05-20T10:00:00Z", "change": "renamed"}],
        "created_at": "2026-05-20T10:00:00Z",
        "updated_at": "2026-05-20T10:05:00Z",
    }
    parsed = WorkspaceSessionOut.model_validate(raw)
    assert parsed.status == "editing"


def test_edit_skill_in():
    obj = EditSkillIn(skill_draft={"prompt": "x"})
    assert obj.skill_draft["prompt"] == "x"


def test_publish_skill_in_optional():
    obj = PublishSkillIn()
    dumped = obj.model_dump(exclude_unset=True)
    assert dumped == {}
