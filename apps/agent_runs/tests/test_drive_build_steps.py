"""Pin _build_steps' step-status inference + _extract_step_statuses.

Ported from ace-web apps/opps/tests/test_build_steps.py. Primary source of
truth is run_state.yaml's declared status (``phases.<phase>.steps.<skill>.
status``); falls back to artifact-presence when no status is declared.
"""
from dataclasses import dataclass

from apps.agent_runs.drive.parsers import (
    ArtifactRef,
    QAResult,
    _build_steps,
    _extract_step_statuses,
)


@dataclass
class _StubSkill:
    name: str
    phase: str = "idea-to-design"
    ordinal: int = 1


def _artifact(name: str, path: str | None = None) -> ArtifactRef:
    return ArtifactRef(
        name=name,
        drive_file_id=f"id-{name}",
        drive_web_link="",
        size_bytes=0,
        mime_type="application/octet-stream",
        path=path or name,
    )


# --- Artifact-presence fallback (run_state.yaml absent / no status field) ---


def test_step_with_real_output_artifact_is_complete():
    skills = [_StubSkill("idea-to-pdd")]
    arts = {"idea-to-pdd": [_artifact("idea-to-pdd.md")]}
    [step] = _build_steps(skills, arts, {}, "folder-id")
    assert step.step.status == "complete"


def test_step_with_only_decisions_yaml_is_pending():
    skills = [_StubSkill("idea-to-pdd")]
    arts = {"idea-to-pdd": [_artifact("decisions.yaml")]}
    [step] = _build_steps(skills, arts, {}, "folder-id")
    assert step.step.status == "pending"


def test_step_with_decisions_yml_variant_is_also_pending():
    skills = [_StubSkill("idea-to-pdd")]
    arts = {"idea-to-pdd": [_artifact("decisions.yml")]}
    [step] = _build_steps(skills, arts, {}, "folder-id")
    assert step.step.status == "pending"


def test_step_with_decisions_plus_real_output_is_complete():
    skills = [_StubSkill("idea-to-pdd")]
    arts = {"idea-to-pdd": [_artifact("decisions.yaml"), _artifact("idea-to-pdd.md")]}
    [step] = _build_steps(skills, arts, {}, "folder-id")
    assert step.step.status == "complete"


def test_step_with_no_artifacts_is_pending():
    skills = [_StubSkill("pdd-to-work-order")]
    [step] = _build_steps(skills, {}, {}, "folder-id")
    assert step.step.status == "pending"


# --- run_state.yaml as primary source of truth ---


def test_run_state_done_marks_complete_without_artifacts():
    skills = [_StubSkill("synthetic-summary", phase="synthetic-data-and-workflows")]
    [step] = _build_steps(
        skills, {}, {}, "folder-id",
        step_status_by_skill={"synthetic-summary": "done"},
    )
    assert step.step.status == "complete"


def test_run_state_complete_marks_complete():
    skills = [_StubSkill("idea-to-pdd")]
    [step] = _build_steps(
        skills, {}, {}, "folder-id",
        step_status_by_skill={"idea-to-pdd": "complete"},
    )
    assert step.step.status == "complete"


def test_run_state_running_surfaces_running():
    skills = [_StubSkill("pdd-to-deliver-app", phase="commcare-setup")]
    [step] = _build_steps(
        skills, {}, {}, "folder-id",
        step_status_by_skill={"pdd-to-deliver-app": "running"},
    )
    assert step.step.status == "running"


def test_run_state_in_progress_normalizes_to_running():
    skills = [_StubSkill("pdd-to-learn-app", phase="commcare-setup")]
    [step] = _build_steps(
        skills, {}, {}, "folder-id",
        step_status_by_skill={"pdd-to-learn-app": "in_progress"},
    )
    assert step.step.status == "running"


def test_run_state_skipped_surfaces_skipped():
    skills = [_StubSkill("llo-invite", phase="solicitation-management")]
    [step] = _build_steps(
        skills, {}, {}, "folder-id",
        step_status_by_skill={"llo-invite": "skipped"},
    )
    assert step.step.status == "skipped"


def test_run_state_no_op_normalizes_to_skipped():
    skills = [_StubSkill("llo-invite", phase="solicitation-management")]
    [step] = _build_steps(
        skills, {}, {}, "folder-id",
        step_status_by_skill={"llo-invite": "no-op"},
    )
    assert step.step.status == "skipped"


def test_run_state_failed_normalizes_to_error():
    skills = [_StubSkill("ocs-chatbot-eval", phase="ocs-setup")]
    [step] = _build_steps(
        skills, {}, {}, "folder-id",
        step_status_by_skill={"ocs-chatbot-eval": "failed"},
    )
    assert step.step.status == "error"


def test_run_state_pending_stays_pending_even_with_artifacts():
    skills = [_StubSkill("idea-to-pdd")]
    arts = {"idea-to-pdd": [_artifact("idea-to-pdd.md")]}
    [step] = _build_steps(
        skills, arts, {}, "folder-id",
        step_status_by_skill={"idea-to-pdd": "pending"},
    )
    assert step.step.status == "pending"


def test_run_state_missing_falls_back_to_artifact_presence():
    skills = [_StubSkill("idea-to-pdd")]
    arts = {"idea-to-pdd": [_artifact("idea-to-pdd.md")]}
    [step] = _build_steps(skills, arts, {}, "folder-id", step_status_by_skill={})
    assert step.step.status == "complete"


def test_run_state_unknown_status_falls_back_to_artifact_presence():
    skills = [_StubSkill("idea-to-pdd")]
    arts = {"idea-to-pdd": [_artifact("idea-to-pdd.md")]}
    [step] = _build_steps(
        skills, arts, {}, "folder-id",
        step_status_by_skill={"idea-to-pdd": "weird-new-status-2031"},
    )
    assert step.step.status == "complete"


# --- _extract_step_statuses helper ---


def test_extract_step_statuses_shape_a_steps_dict():
    state = {
        "phases": {
            "commcare-setup": {
                "status": "running",
                "steps": {
                    "pdd-to-learn-app": {"status": "done", "artifacts": {"app_id": "abc"}},
                    "pdd-to-deliver-app": {"status": "running"},
                    "app-deploy": {"status": "pending"},
                },
            },
        },
    }
    out = _extract_step_statuses(state)
    assert out == {
        "pdd-to-learn-app": "done",
        "pdd-to-deliver-app": "running",
        "app-deploy": "pending",
    }


def test_extract_step_statuses_shape_b_bare_strings():
    state = {
        "phases": {
            "idea-to-design": {"idea-to-pdd": "done", "pdd-to-work-order": "pending"},
        },
    }
    out = _extract_step_statuses(state)
    assert out == {"idea-to-pdd": "done", "pdd-to-work-order": "pending"}


def test_extract_step_statuses_skips_phase_level_status_key():
    state = {
        "phases": {
            "ocs-setup": {"status": "complete", "steps": {"ocs-agent-setup": {"status": "done"}}},
        },
    }
    out = _extract_step_statuses(state)
    assert "status" not in out
    assert out == {"ocs-agent-setup": "done"}


def test_extract_step_statuses_handles_missing_phases():
    assert _extract_step_statuses({}) == {}
    assert _extract_step_statuses({"phases": None}) == {}
    assert _extract_step_statuses({"phases": "bogus"}) == {}


def test_extract_step_statuses_handles_malformed_phase_entries():
    state = {
        "phases": {
            "broken-phase": "complete",  # malformed; should be a dict
            "good-phase": {"steps": {"good-skill": {"status": "done"}}},
        },
    }
    out = _extract_step_statuses(state)
    assert out == {"good-skill": "done"}


# --- Cross-check semantics (QA-fail overrides) ---


def test_qa_failed_overrides_run_state_complete():
    skills = [_StubSkill("ocs-chatbot-qa", phase="ocs-setup")]
    qa = {
        "ocs-chatbot-qa": QAResult(
            skill="ocs-chatbot-qa", target_skill="ocs-chatbot-qa", verdict="fail",
        ),
    }
    arts = {"ocs-chatbot-qa": [_artifact("ocs-chatbot-qa.md")]}
    [step] = _build_steps(
        skills, arts, {}, "folder-id",
        qa_results_by_skill=qa,
        step_status_by_skill={"ocs-chatbot-qa": "done"},
    )
    assert step.step.status == "qa-failed"
