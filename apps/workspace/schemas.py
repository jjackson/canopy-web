"""Pydantic schemas for the /api/v2/workspace surface.

Streaming endpoints (POST /workspace/start/<id>/ and
POST /workspace/analyze/<id>/) produce text/event-stream and do
NOT have a Pydantic response schema. They're declared in apps/workspace/api.py
with `response=None` and documented inline.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from apps.common.schemas import StrictModel

WorkspaceStatus = Literal[
    "created", "analyzing", "proposed", "editing", "testing", "published"
]


class WorkspaceSessionListItemOut(StrictModel):
    id: int
    collection_id: int
    collection_name: str | None
    status: WorkspaceStatus
    skill_name: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class WorkspaceSessionOut(StrictModel):
    id: int
    collection_id: int
    status: WorkspaceStatus
    proposed_approach: dict = Field(default_factory=dict)
    proposed_eval_cases: list = Field(default_factory=list)
    skill_draft: dict = Field(default_factory=dict)
    edit_history: list = Field(default_factory=list)
    created_at: dt.datetime
    updated_at: dt.datetime


class EditSkillIn(StrictModel):
    skill_draft: dict
    note: str | None = None


class PublishSkillIn(StrictModel):
    """Optional override for the published skill name."""
    name: str | None = None
