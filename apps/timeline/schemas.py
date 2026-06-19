"""Pydantic schemas for the /api/timeline surface (read-only aggregator)."""
from __future__ import annotations

import datetime as dt

from apps.common.schemas import StrictModel


class ActivityEventOut(StrictModel):
    subsystem: str
    kind: str
    at: dt.datetime
    title: str
    summary: str | None = None
    project_slug: str | None = None
    actor: str | None = None
    href: str
    external: bool = False
    icon: str | None = None
    id: str


class SubsystemOut(StrictModel):
    key: str
    label: str


class TimelineOut(StrictModel):
    events: list[ActivityEventOut]
    # The filter catalog for the rail (stable order, labels live server-side).
    subsystems: list[SubsystemOut]
    # Opaque compound cursor for "show more": pass back verbatim as ?before=.
    # Null when the page is the tail.
    next_before: str | None = None
