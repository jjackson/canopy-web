"""Pydantic schemas for the /api/shareouts surface."""
from __future__ import annotations

import datetime as dt

from pydantic import Field

from apps.common.schemas import StrictModel


class ShareoutLink(StrictModel):
    label: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=500)


class ShareoutIn(StrictModel):
    """One briefing in a POST batch. `project_slug` omitted/null = roll-up."""

    project_slug: str | None = None
    period_start: dt.date
    period_end: dt.date
    title: str = Field(min_length=1, max_length=200)
    summary: str = ""
    content: str = Field(min_length=1)
    links: list[ShareoutLink] = Field(default_factory=list)
    author: str = Field(default="", max_length=100)
    source: str = Field(min_length=1, max_length=100)


class ShareoutBatchIn(StrictModel):
    shareouts: list[ShareoutIn] = Field(min_length=1)


class ShareoutBatchOut(StrictModel):
    created: int
    replaced: int
    skipped: int


class ShareoutOut(StrictModel):
    id: int
    project_slug: str | None = None
    project_name: str | None = None
    period_start: dt.date
    period_end: dt.date
    title: str
    summary: str
    content: str
    links: list[ShareoutLink] = Field(default_factory=list)
    author: str
    source: str
    created_at: dt.datetime
