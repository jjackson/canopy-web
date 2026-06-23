"""Pydantic schemas for the canopy.origin issue-record API."""
from __future__ import annotations

import datetime as dt

from pydantic import Field

from apps.common.schemas import StrictModel


class OriginIssueIn(StrictModel):
    """Upsert payload — the canopy.origin record minus envelope fields (`schema`/`issue` are derived)."""

    repo: str = Field(min_length=1, max_length=200)
    number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    source: str = "hal-architect"
    agent: str = "hal"
    skill: str = "architect"
    initiative: str = ""
    ledger: str = ""
    created: str = ""
    disposition: str = "route"
    confidence: str = "medium"
    mandate: str = ""
    done_when: str = ""
    intent: str = ""
    evidence: list[dict] = Field(default_factory=list)   # pointers only — claim → session path
    corpus: dict = Field(default_factory=dict)           # {sessions_scanned, cross_user, drilled:[paths]}


class OriginIssueOut(StrictModel):
    id: int
    repo: str
    number: int
    title: str
    source: str
    agent: str
    skill: str
    initiative: str
    ledger: str
    created: str
    disposition: str
    confidence: str
    mandate: str
    done_when: str
    intent: str
    evidence: list[dict]
    corpus: dict
    created_at: dt.datetime
    updated_at: dt.datetime
