"""Pin _parse_decision_rows / _extract_decision_rows across v1-v4 schemas.

Ported from ace-web apps/opps/tests/test_parse_decision_rows.py to prove
parity of the decisions-log parsing in canopy-web's Drive adapter substrate.

The v3 schema renamed `options_considered` -> `options` and `notes` ->
`reasoning`. v2 uses `ai-default` + optional `override`. v1 used `default`
+ `applied`/`open` statuses. The reader maps all to one internal `Decision`
and falls back v3 -> v2 -> v1, warning when an id-bearing row is missing
question/ai-default (the schema-drift regression signature).
"""
import logging

from canopy_runs.drive.parsers import _extract_decision_rows, _parse_decision_rows

_LOGGER = "canopy_runs.drive.parsers"


def _base_row(extras: dict | None = None) -> dict:
    row = {
        "id": "row-1",
        "phase": "idea-to-design",
        "skill": "idea-to-pdd",
        "question": "Which language?",
        "options_considered": ["english", "french"],
        "source": "src",
        "notes": "",
    }
    if extras:
        row.update(extras)
    return row


def test_v1_row_maps_default_to_ai_default():
    rows = [_base_row({"default": "english", "status": "applied"})]
    [d] = _parse_decision_rows(rows)
    assert d.ai_default == "english"
    assert d.override == ""
    assert d.status == "ai-default"


def test_v1_open_status_maps_to_ai_default():
    rows = [_base_row({"default": "english", "status": "open"})]
    [d] = _parse_decision_rows(rows)
    assert d.status == "ai-default"


def test_v2_row_with_only_ai_default():
    rows = [_base_row({"ai-default": "english", "status": "ai-default"})]
    [d] = _parse_decision_rows(rows)
    assert d.ai_default == "english"
    assert d.override == ""
    assert d.status == "ai-default"


def test_v2_row_with_override():
    rows = [_base_row({
        "ai-default": "english",
        "override": "french",
        "status": "overridden",
    })]
    [d] = _parse_decision_rows(rows)
    assert d.ai_default == "english"
    assert d.override == "french"
    assert d.status == "overridden"


def test_row_with_neither_default_nor_ai_default_surfaces_empty():
    rows = [_base_row({"status": "ai-default"})]
    [d] = _parse_decision_rows(rows)
    assert d.ai_default == ""
    assert d.override == ""


def test_row_missing_id_is_dropped():
    rows = [_base_row({"id": "", "default": "x", "status": "ai-default"})]
    assert _parse_decision_rows(rows) == []


def test_non_dict_rows_are_dropped():
    assert _parse_decision_rows(["string", 42, None]) == []


def test_v3_row_reads_options_field():
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd",
        "question": "Which language?", "ai-default": "english",
        "options": ["english", "french"], "source": "src", "status": "ai-default",
    }
    [d] = _parse_decision_rows([row])
    assert d.options_considered == ["english", "french"]


def test_v3_row_reads_reasoning_field():
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd",
        "question": "Which language?", "ai-default": "english", "options": [],
        "source": "src", "status": "ai-default",
        "reasoning": "english is the working language per LLO directory",
    }
    [d] = _parse_decision_rows([row])
    assert d.notes == "english is the working language per LLO directory"


def test_v2_options_considered_still_parses_for_back_compat():
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd",
        "question": "Which language?", "ai-default": "english",
        "options_considered": ["english", "french"], "source": "src",
        "status": "ai-default", "notes": "old-style reasoning",
    }
    [d] = _parse_decision_rows([row])
    assert d.options_considered == ["english", "french"]
    assert d.notes == "old-style reasoning"


def test_warns_when_row_has_id_but_missing_question(caplog):
    """The bednet regression signature: id + phase but no question/ai-default
    because the writer used wrong field names. Surface the row AND warn."""
    bad_row = {
        "id": "wo-001", "phase": "idea-to-design", "skill": "pdd-to-work-order",
        "decision": "Payment rate set to TBD",  # wrong key
        "rationale": "Smoke test",  # wrong key
    }
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        [d] = _parse_decision_rows([bad_row])
    assert d.id == "wo-001"
    assert d.question == ""
    assert d.ai_default == ""
    assert any(
        "wo-001" in r.message and "question" in r.message for r in caplog.records
    )


def test_v3_row_reads_override_reasoning():
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd",
        "question": "Which language?", "ai-default": "english", "override": "french",
        "options": ["english", "french"], "source": "src", "status": "overridden",
        "reasoning": "english per LLO directory",
        "override_reasoning": "LLO confirmed french is the working language",
    }
    [d] = _parse_decision_rows([row])
    assert d.override == "french"
    assert d.override_reasoning == "LLO confirmed french is the working language"
    assert d.notes == "english per LLO directory"


def test_override_reasoning_falls_back_to_hyphenated_key():
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd", "question": "Q?",
        "ai-default": "a", "override": "b", "options": ["a", "b"], "source": "src",
        "status": "overridden", "override-reasoning": "human picked b",
    }
    [d] = _parse_decision_rows([row])
    assert d.override_reasoning == "human picked b"


def test_override_reasoning_defaults_to_empty():
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd", "question": "Q?",
        "ai-default": "a", "options": ["a"], "source": "src", "status": "ai-default",
    }
    [d] = _parse_decision_rows([row])
    assert d.override_reasoning == ""


def test_extract_decision_rows_canonical_key():
    data = {"schema_version": 3, "decisions": [{"id": "row-1"}, {"id": "row-2"}]}
    assert _extract_decision_rows(data) == [{"id": "row-1"}, {"id": "row-2"}]


def test_extract_decision_rows_legacy_rows_key_with_warning(caplog):
    data = {"schema_version": 3, "rows": [{"id": "row-1"}, {"id": "row-2"}]}
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        rows = _extract_decision_rows(data)
    assert rows == [{"id": "row-1"}, {"id": "row-2"}]
    assert any(
        "rows:" in r.message and "decisions:" in r.message and "ace#529" in r.message
        for r in caplog.records
    )


def test_extract_decision_rows_canonical_wins_when_both_present():
    data = {"decisions": [{"id": "from-decisions"}], "rows": [{"id": "from-rows"}]}
    assert _extract_decision_rows(data) == [{"id": "from-decisions"}]


def test_extract_decision_rows_returns_empty_when_neither_key_set():
    assert _extract_decision_rows({}) == []
    assert _extract_decision_rows({"schema_version": 3}) == []
    assert _extract_decision_rows({"decisions": "not a list"}) == []
    assert _extract_decision_rows({"rows": "not a list"}) == []


def test_legacy_rows_full_loader_integration():
    """End-to-end: the bednet-shape malformed file parses to populated
    Decision dataclasses via the same path the loader uses."""
    import yaml as _yaml

    malformed = """schema_version: 3
opportunity: bednet
run_id: '20260527-0253'
rows:
  - id: archetype-selection
    phase: 1-design
    skill: idea-to-pdd
    question: Q?
    ai-default: atomic-visit
    options: [atomic-visit, focus-group]
    source: src
    status: ai-default
    reasoning: r
"""
    data = _yaml.safe_load(malformed)
    rows = _parse_decision_rows(_extract_decision_rows(data))
    assert len(rows) == 1
    assert rows[0].id == "archetype-selection"
    assert rows[0].ai_default == "atomic-visit"
    assert rows[0].options_considered == ["atomic-visit", "focus-group"]


def test_v4_row_reads_evidence_basis_and_conflict_signals():
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd",
        "question": "How many visit instruments?", "ai-default": "two linked forms",
        "options": ["one form", "two linked forms"], "source": "src",
        "status": "ai-default", "evidence_basis": "conflicting",
        "conflict_signals": [
            "source says households are visited twice",
            "source describes only one visit instrument",
        ],
    }
    [d] = _parse_decision_rows([row])
    assert d.evidence_basis == "conflicting"
    assert d.conflict_signals == [
        "source says households are visited twice",
        "source describes only one visit instrument",
    ]


def test_evidence_basis_defaults_to_stated_for_legacy_v3_rows():
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd", "question": "Q?",
        "ai-default": "a", "options": ["a"], "source": "src", "status": "ai-default",
    }
    [d] = _parse_decision_rows([row])
    assert d.evidence_basis == "stated"
    assert d.conflict_signals == []


def test_evidence_basis_unknown_value_falls_back_to_stated():
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd", "question": "Q?",
        "ai-default": "a", "options": ["a"], "source": "src", "status": "ai-default",
        "evidence_basis": "WILD-GUESS",
    }
    [d] = _parse_decision_rows([row])
    assert d.evidence_basis == "stated"


def test_evidence_basis_is_case_insensitive():
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd", "question": "Q?",
        "ai-default": "a", "options": ["a"], "source": "src", "status": "ai-default",
        "evidence_basis": "Inferred",
    }
    [d] = _parse_decision_rows([row])
    assert d.evidence_basis == "inferred"


def test_conflict_signals_non_list_coerces_to_empty():
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd", "question": "Q?",
        "ai-default": "a", "options": ["a"], "source": "src", "status": "ai-default",
        "evidence_basis": "conflicting", "conflict_signals": "not a list",
    }
    [d] = _parse_decision_rows([row])
    assert d.conflict_signals == []


def test_no_warning_for_well_formed_row(caplog):
    row = {
        "id": "row-1", "phase": "1-design", "skill": "idea-to-pdd",
        "question": "Which language?", "ai-default": "english", "options": ["english"],
        "source": "src", "status": "ai-default",
    }
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        _parse_decision_rows([row])
    assert not any("missing" in r.message for r in caplog.records)
