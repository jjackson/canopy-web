"""Pydantic schemas for the /api/v2/skills surface."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from apps.common.schemas import StrictModel

EvalTrend = Literal["improving", "declining", "stable"] | None
RuntimeName = Literal["web", "claude_code", "open_claw"]


class SkillOut(StrictModel):
    id: int
    name: str
    description: str = ""
    definition: dict
    version: int = Field(ge=1)
    usage_count: int = Field(ge=0)
    eval_score: float | None = None
    eval_trend: EvalTrend = None
    last_eval_at: dt.datetime | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class AdapterIn(StrictModel):
    runtime: RuntimeName


class AdapterOut(StrictModel):
    runtime: RuntimeName
    content: str  # rendered adapter artifact (string body)
    format: Literal["markdown", "json", "yaml"]
