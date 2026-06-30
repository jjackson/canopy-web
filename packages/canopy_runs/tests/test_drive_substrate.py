"""Verdict + QA parsing parity, and the FakeDriveClient corpus engine.

Proves the ported verdict-score normalization, QA-result parsing, and that
FakeDriveClient serves a nested-dict run-folder tree through canopy-web's
DriveClient Protocol (read + write + changes feed).
"""
from canopy_runs.drive.client import DriveClient, FileContent
from canopy_runs.drive.parsers import (
    _detect_score_scale,
    _parse_qa_result_yaml,
    _parse_verdict_yaml,
    _skill_from_verdict_producer,
    _skill_from_verdict_stem,
    parse_decisions_yaml,
)
from tests.fixtures.fake_drive import (
    FakeDriveClient,
    malaria_pilot_tree,
    turmeric_multi_run_tree,
)

# --- Verdict parsing ---


def test_verdict_old_short_shape():
    v = _parse_verdict_yaml("score: 8.5\npassed: true\nevaluated_at: 2026-04-15T10:00:00Z\n")
    assert v is not None
    assert v.passed is True
    # 8.5 with no declared scale: magnitude heuristic leaves it as-is here
    # (no scale field → no normalization), so score stays 8.5.
    assert v.score == 8.5


def test_verdict_overall_score_and_verdict_string():
    v = _parse_verdict_yaml("overall_score: 87\nverdict: pass\nsummary: healthy\n")
    assert v.score == 87.0
    assert v.passed is True
    assert v.rationale == "healthy"


def test_verdict_fail_string_maps_passed_false():
    v = _parse_verdict_yaml("overall_score: 40\nverdict: fail\n")
    assert v.passed is False


def test_verdict_score_normalized_via_declared_scale():
    body = "overall_score: 3\ndimensions:\n  correctness:\n    score: 3\n    scale: '0-3'\n"
    v = _parse_verdict_yaml(body)
    # 3 on a 0-3 scale normalizes to 100.
    assert v.score == 100.0


def test_verdict_dimensions_pass_through_as_criteria():
    body = "overall_score: 82\nverdict: pass\ndimensions:\n  design: {score: 88}\n"
    v = _parse_verdict_yaml(body)
    assert v.criteria == {"design": {"score": 88}}


def test_verdict_malformed_yaml_returns_none():
    assert _parse_verdict_yaml(": : not yaml :\n  - [") is None


def test_detect_score_scale_picks_max():
    data = {"dimensions": {"a": {"scale": "0-10"}, "b": {"scale": "0-100"}}}
    assert _detect_score_scale(data) == 100.0


def test_detect_score_scale_none_when_absent():
    assert _detect_score_scale({"overall_score": 5}) is None


def test_skill_from_verdict_stem_strips_variant():
    assert _skill_from_verdict_stem("ocs-chatbot-eval-deep") == "ocs-chatbot-eval"
    assert _skill_from_verdict_stem("opp-eval-monitor") == "opp-eval"
    assert _skill_from_verdict_stem("idea-to-pdd") == "idea-to-pdd"


def test_skill_from_verdict_producer_eval_suffix_and_self_eval():
    registered = {"idea-to-pdd", "opp-eval"}
    assert _skill_from_verdict_producer("idea-to-pdd-eval", registered) == "idea-to-pdd"
    assert _skill_from_verdict_producer("opp-eval", registered) == "opp-eval"
    assert _skill_from_verdict_producer("phantom-eval", registered) is None


# --- QA result parsing ---


def test_qa_result_pass():
    r = _parse_qa_result_yaml("verdict: pass\nran_at: 2026-04-15T10:00:00Z\n", "idea-to-pdd-qa")
    assert r is not None
    assert r.verdict == "pass"
    assert r.target_skill == "idea-to-pdd"
    assert r.skill == "idea-to-pdd-qa"


def test_qa_result_fail_with_failures_and_stats():
    body = (
        "verdict: fail\n"
        "stats: {checks_run: 5, checks_passed: 3, checks_failed: 2}\n"
        "failures:\n"
        "  - check: em-outcomes\n"
        "    type: static\n"
        "    detail: only 2 outcomes\n"
        "    auto_fix_hint: add a third outcome\n"
    )
    r = _parse_qa_result_yaml(body, "idea-to-pdd-qa")
    assert r.verdict == "fail"
    assert r.checks_run == 5
    assert r.checks_failed == 2
    assert len(r.failures) == 1
    assert r.failures[0].check == "em-outcomes"
    assert r.failures[0].auto_fix_hint == "add a third outcome"


def test_qa_result_unknown_verdict_returns_none():
    assert _parse_qa_result_yaml("verdict: maybe\n", "idea-to-pdd-qa") is None


# --- FakeDriveClient corpus engine ---


def test_fake_drive_satisfies_protocol():
    client = FakeDriveClient.from_tree(malaria_pilot_tree())
    assert isinstance(client, DriveClient)


def test_fake_drive_lists_and_reads_run_state():
    client = FakeDriveClient.from_tree(malaria_pilot_tree())
    opp_id = client.folder_id("ACE/malaria-pilot")
    children = client.list_folder(opp_id)
    names = {f.name for f in children}
    assert "run_state.yaml" in names
    assert "app-summaries" in names

    state_file = next(f for f in children if f.name == "run_state.yaml")
    content = client.get_content(state_file.id, state_file.mime_type)
    assert isinstance(content, FileContent)
    assert "current_phase: app-building" in content.content


def test_fake_drive_recursive_paths_carry_subfolder_prefix():
    client = FakeDriveClient.from_tree(malaria_pilot_tree())
    opp_id = client.folder_id("ACE/malaria-pilot")
    tree = client.list_files(opp_id, recursive=True)
    paths = {f.path for f in tree}
    assert "app-summaries/learn-app-brief.md" in paths
    assert "closeout/cycle-grade.md" in paths


def test_fake_drive_multi_run_verdict_parses_to_judge_verdict():
    client = FakeDriveClient.from_tree(turmeric_multi_run_tree())
    vfile = client.file_id("ACE/turmeric/runs/20260502-1830/verdicts/idea-to-pdd-deep.yaml")
    body = client.get_content(vfile, "application/x-yaml").content
    v = _parse_verdict_yaml(body)
    assert v.score == 87.0
    assert v.passed is True


def test_fake_drive_write_then_read_round_trip_and_changes():
    client = FakeDriveClient.from_tree(turmeric_multi_run_tree())
    run_id = client.folder_id("ACE/turmeric/runs/20260502-1830")
    token = client.get_changes_start_page_token()

    new_id = client.upload_file(run_id, "decisions.yaml", "decisions: []\n", "application/x-yaml")
    assert client.get_content(new_id, "application/x-yaml").content == "decisions: []\n"

    page = client.list_changes(token)
    assert new_id in page.changed_file_ids
    assert page.expired is False


def test_fake_drive_decisions_round_trip_through_parser():
    """A decisions.yaml written into the fake parses back via the parser —
    the parity corpus closes the loop end to end."""
    client = FakeDriveClient.from_tree(turmeric_multi_run_tree())
    run_id = client.folder_id("ACE/turmeric/runs/20260502-1830")
    body = (
        "schema_version: 3\n"
        "decisions:\n"
        "  - id: archetype-selection\n"
        "    phase: 1-design\n"
        "    skill: idea-to-pdd\n"
        "    question: Which archetype?\n"
        "    ai-default: atomic-visit\n"
        "    options: [atomic-visit, focus-group]\n"
        "    source: src\n"
        "    status: ai-default\n"
    )
    fid = client.upload_file(run_id, "decisions.yaml", body, "application/x-yaml")
    read_back = client.get_content(fid, "application/x-yaml").content
    rows = parse_decisions_yaml(read_back)
    assert len(rows) == 1
    assert rows[0].id == "archetype-selection"
    assert rows[0].options_considered == ["atomic-visit", "focus-group"]
