"""Pydantic schemas for the /api/tokens/ surface."""
from __future__ import annotations

import datetime as dt

from pydantic import Field

from apps.common.schemas import StrictModel


class PersonalTokenOut(StrictModel):
    """A token as listed to its owner. Never contains the raw value."""
    id: int
    label: str
    created_at: dt.datetime
    last_used_at: dt.datetime | None = None
    revoked_at: dt.datetime | None = None


class PersonalTokenCreateIn(StrictModel):
    label: str = Field(min_length=1, max_length=200)


class PersonalTokenCreatedOut(PersonalTokenOut):
    """Returned exactly once at creation — includes the raw token."""
    raw: str
