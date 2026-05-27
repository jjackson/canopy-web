"""Pydantic schemas for the /api/evals surface."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from apps.common.schemas import StrictModel

EvalRunStatus = Literal["pending", "running", "completed", "failed"]
RuntimeName = Literal["web", "claude_code", "open_claw"]


class EvalCaseOut(StrictModel):
    id: int
    name: str
    input_data: dict
    expected_output: dict
    source_excerpt: str = ""
    created_at: dt.datetime


class EvalCaseCreateIn(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    input_data: dict
    expected_output: dict
    source_excerpt: str = ""


class EvalCasePatchIn(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    input_data: dict | None = None
    expected_output: dict | None = None
    source_excerpt: str | None = None


class EvalRunOut(StrictModel):
    id: int
    status: EvalRunStatus
    results: dict
    overall_score: float | None = None
    # `runtime` is a free-form CharField on EvalRun — historical rows have
    # stored elapsed-time strings (e.g. "1.23s") alongside the conventional
    # runtime names. Schema is permissive on the response side.
    runtime: str = "web"
    created_at: dt.datetime


class EvalRunIn(StrictModel):
    """Body of POST /evals/<id>/run/."""
    runtime: RuntimeName = "web"


class EvalSuiteOut(StrictModel):
    id: int
    cases: list[EvalCaseOut]
    runs: list[EvalRunOut]
    created_at: dt.datetime
