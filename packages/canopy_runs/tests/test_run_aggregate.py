"""Run-level eval aggregate over a run's verdicts (the opp-eval analogue).

`overall_score` is weakest-link (min) across judge verdicts; `qa_gate_ok` is
False iff any QA verdict explicitly failed. Both are computed (serialized) fields
so the REST read model surfaces them without a stored column.
"""
from canopy_runs.schemas import Run, Step, Verdict


def _run(verdicts):
    return Run(
        id="r1", agent_slug="echo",
        steps=[Step(key="s1", ordinal=0)],
        verdicts=verdicts,
    )


def test_overall_score_is_weakest_link_over_judge_verdicts():
    run = _run([
        Verdict(step_key="s1", kind="judge", score=88.0),
        Verdict(step_key="s2", kind="judge", score=72.0),
    ])
    assert run.overall_score == 72.0


def test_overall_score_ignores_qa_and_unscored_verdicts():
    run = _run([
        Verdict(step_key="s1", kind="judge", score=90.0),
        Verdict(step_key="s1", kind="qa", passed=True),        # qa excluded
        Verdict(step_key="s2", kind="judge", score=None),       # unscored excluded
    ])
    assert run.overall_score == 90.0


def test_overall_score_none_when_no_judge_scores():
    assert _run([Verdict(step_key="s1", kind="qa", passed=True)]).overall_score is None


def test_qa_gate_ok_true_when_no_qa_failed():
    run = _run([
        Verdict(step_key="s1", kind="qa", passed=True),
        Verdict(step_key="s2", kind="judge", score=50.0),
    ])
    assert run.qa_gate_ok is True


def test_qa_gate_ok_false_when_any_qa_failed():
    run = _run([
        Verdict(step_key="s1", kind="qa", passed=True),
        Verdict(step_key="s2", kind="qa", passed=False),
    ])
    assert run.qa_gate_ok is False


def test_qa_failed_step_judge_score_excluded_from_overall():
    # s1 was judged a LOW 40 but its QA failed → that score is invalid and must
    # be excluded; without the rule weakest-link would wrongly report 40. With
    # it, only the qa-clean s2 (70) counts → overall 70, gate red.
    run = _run([
        Verdict(step_key="s1", kind="judge", score=40.0),
        Verdict(step_key="s1", kind="qa", passed=False),
        Verdict(step_key="s2", kind="judge", score=70.0),
        Verdict(step_key="s2", kind="qa", passed=True),
    ])
    assert run.overall_score == 70.0
    assert run.qa_gate_ok is False


def test_overall_none_when_only_judged_step_failed_qa():
    run = _run([
        Verdict(step_key="s1", kind="judge", score=95.0),
        Verdict(step_key="s1", kind="qa", passed=False),
    ])
    assert run.overall_score is None
    assert run.qa_gate_ok is False


def test_aggregate_fields_are_serialized():
    run = _run([Verdict(step_key="s1", kind="judge", score=80.0)])
    dumped = run.model_dump()
    assert dumped["overall_score"] == 80.0
    assert dumped["qa_gate_ok"] is True
