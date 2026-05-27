"""Pydantic schemas for the /api/workspace surface.

The /start/ endpoint produces text/event-stream and does NOT have a Pydantic
response schema.  It is declared in apps/workspace/api.py with `response=None`
and documented inline.

The /analyze/ endpoint is a synchronous JSON endpoint; its response is
described by :class:`WorkspaceAnalyzeOut`.
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


class WorkspaceAnalyzeOut(StrictModel):
    """Synchronous response from POST /workspace/analyze/{collection_id}/.

    NOT an SSE stream — returns the parsed proposal directly.
    """
    session_id: int
    status: WorkspaceStatus
    approach: dict
    eval_cases: list
