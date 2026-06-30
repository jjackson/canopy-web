"""Pydantic schemas for the /api/workspaces surface."""
from __future__ import annotations

import datetime as dt

from pydantic import Field

from apps.common.schemas import StrictModel


class WorkspaceCreateIn(StrictModel):
    slug: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=200)
    auto_join_domains: list[str] = Field(default_factory=list)


class WorkspaceOut(StrictModel):
    slug: str
    display_name: str
    auto_join_domains: list[str]
    role: str  # the requesting user's role in this workspace
    created_at: dt.datetime
