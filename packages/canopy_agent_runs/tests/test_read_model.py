"""Read-model + status-derivation tests (no DB needed)."""
from __future__ import annotations

import datetime as dt

from canopy_agent_runs.schemas import Gate, Run, Step, derive_status


def _step(key: str, status: str, ordinal: int = 0) -> Step:
    return Step(key=key, status=status, ordinal=ordinal)


def test_derive_status_empty_is_pending():
    assert derive_status([]) == "pending"


def test_derive_status_all_terminal_is_complete():
    steps = [_step("a", "complete", 0), _step("b", "skipped", 1)]
    assert derive_status(steps) == "complete"


def test_derive_status_any_nonterminal_is_in_progress():
    steps = [_step("a", "complete", 0), _step("b", "running", 1)]
    assert derive_status(steps) == "in_progress"


def test_failed_step_is_not_terminal_for_status():
    # failed is not in TERMINAL_STEP_STATUSES → run is still in_progress
    steps = [_step("a", "complete", 0), _step("b", "failed", 1)]
    assert derive_status(steps) == "in_progress"


def test_run_with_derived_status_recomputes():
    run = Run(
        id="1", agent_slug="echo", status="pending",
        steps=[_step("a", "complete", 0), _step("b", "complete", 1)],
    )
    assert run.with_derived_status().status == "complete"


def test_gate_is_open_when_undecided():
    assert Gate(step_key="a").is_open is True
    decided = Gate(step_key="a", decided_at=dt.datetime.now(dt.timezone.utc))
    assert decided.is_open is False
