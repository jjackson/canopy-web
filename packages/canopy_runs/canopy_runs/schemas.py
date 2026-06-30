"""The storage-agnostic read model for the unified agent run lifecycle.

These are plain Pydantic models (StrictModel style) — the shared contract BOTH
the DB adapter and the Drive adapter return. They are deliberately NOT tied to any
ORM: a DB adapter hydrates them from rows; the Drive adapter parses them from
ACE's `run_state.yaml` / `verdicts/` / `decisions.yaml` trees. See the design
spec §3.

Run.status is a DERIVED field — `derive_status()` computes it from the steps map
(all terminal → complete; any running/pending → in_progress) rather than reading a
stored column. This is load-bearing per the ACE source.

Django-free: this module (and the whole `canopy_runs` package) imports no Django.
`StrictModel` is defined locally rather than pulled from `apps.common.schemas` so
the read model is portable into any project (e.g. ace-web) by pip-install alone.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class StrictModel(BaseModel):
    """Strict base: reject unknown fields, hydrate from attributes (ORM rows /
    dataclasses), strip whitespace. Local copy of canopy-web's
    `apps.common.schemas.StrictModel` so the package carries no Django coupling."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


# ---- enums (mirrors of the model choices, kept storage-agnostic) ----
RunMode = Literal["review", "auto"]
RunStatus = Literal["pending", "in_progress", "complete"]
StepStatus = Literal["pending", "running", "complete", "failed", "skipped"]
VerdictKind = Literal["judge", "qa"]
DecisionStatus = Literal["ai-default", "overridden"]

# Steps in a terminal state for the purpose of run-status derivation.
TERMINAL_STEP_STATUSES = {"complete", "skipped"}


class Verdict(StrictModel):
    """A judge or QA verdict attached to a step (QA gates the judge)."""

    step_key: str
    kind: VerdictKind
    score: float | None = None
    passed: bool | None = None
    criteria: dict = Field(default_factory=dict)
    rationale: str = ""
    evaluated_at: dt.datetime | None = None


class Artifact(StrictModel):
    """A step-attributed artifact (many per step)."""

    step_key: str
    name: str
    url: str = ""
    mime_type: str = ""
    size: int | None = None
    role: str = ""
    # ``ref`` is an opaque, adapter-defined stable handle: the Drive adapter sets
    # it to the Drive file id; the DB adapter may set it to the row pk or leave
    # "". ``path`` is the run-relative path (e.g. "1-design/pdd.md"). Both are
    # populated from data each adapter already holds — surfaced so consumers
    # (e.g. ace-web) need not re-derive them downstream.
    ref: str = ""
    path: str = ""


class Decision(StrictModel):
    """An entry in the auditable decisions log."""

    step_key: str
    question: str
    ai_default: str = ""
    override: str = ""
    status: DecisionStatus = "ai-default"
    reasoning: str = ""
    evidence_basis: str = ""
    # Generic decisions-log fields the Drive adapter already parses (ported from
    # ACE's decisions-schema). Storage-agnostic with safe defaults: the DB
    # adapter leaves them at their defaults.
    id: str = ""
    phase: str = ""
    options_considered: list[str] = Field(default_factory=list)
    source: str = ""
    override_reasoning: str = ""
    conflict_signals: list[str] = Field(default_factory=list)


class Gate(StrictModel):
    """A pause point on a step. `decided_at is None` → the gate is still open."""

    step_key: str
    decision: str = ""
    decided_by: str = ""
    decided_at: dt.datetime | None = None
    note: str = ""

    @property
    def is_open(self) -> bool:
        return self.decided_at is None


class Step(StrictModel):
    """One ordered step of a run."""

    key: str
    ordinal: int = 0
    title: str = ""
    status: StepStatus = "pending"
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    error: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STEP_STATUSES


class RunSummary(StrictModel):
    """A lightweight run header for list views (no steps/artifacts/verdicts)."""

    id: str
    agent_slug: str
    label: str = ""
    mode: RunMode = "review"
    status: RunStatus = "pending"
    current_phase: str = ""
    current_step: str = ""
    forked_from: str | None = None
    session_link: str = ""
    created_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None


class Run(StrictModel):
    """The full run read model: header + steps + their attached objects.

    `status` is derived — callers should set it via `derive_status()` after
    populating `steps`, or read `Run.status_from_steps()`.
    """

    id: str
    agent_slug: str
    label: str = ""
    mode: RunMode = "review"
    status: RunStatus = "pending"
    current_phase: str = ""
    current_step: str = ""
    forked_from: str | None = None
    session_link: str = ""
    created_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    steps: list[Step] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    verdicts: list[Verdict] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    gates: list[Gate] = Field(default_factory=list)

    @computed_field
    @property
    def overall_score(self) -> float | None:
        """Weakest-link (min) score across judge verdicts — the opp-eval roll-up.
        QA gates the judge: a judge score on a step whose QA failed is excluded
        (invalid). None when no qa-clean judge verdict carries a score."""
        qa_failed = {v.step_key for v in self.verdicts if v.kind == "qa" and v.passed is False}
        scores = [
            v.score for v in self.verdicts
            if v.kind == "judge" and v.score is not None and v.step_key not in qa_failed
        ]
        return min(scores) if scores else None

    @computed_field
    @property
    def qa_gate_ok(self) -> bool:
        """False iff any QA verdict explicitly failed (QA gates the judge)."""
        return all(v.passed is not False for v in self.verdicts if v.kind == "qa")

    def status_from_steps(self) -> RunStatus:
        """Derive run status from the steps map (load-bearing per spec §3)."""
        return derive_status(self.steps)

    def with_derived_status(self) -> "Run":
        """Return a copy with `status` set to the derived value."""
        return self.model_copy(update={"status": self.status_from_steps()})


def derive_status(steps: list[Step]) -> RunStatus:
    """All terminal → complete; any non-terminal → in_progress; none → pending."""
    if not steps:
        return "pending"
    if all(s.is_terminal for s in steps):
        return "complete"
    return "in_progress"
