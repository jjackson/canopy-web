"""Pydantic schemas for the /api/v2/collections surface."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from apps.common.schemas import StrictModel

SourceType = Literal["slack", "transcript", "document", "text"]

MAX_SOURCE_SIZE = 1_000_000  # 1MB — mirrors the DRF serializer limit


class SourceOut(StrictModel):
    id: int
    source_type: SourceType
    title: str = ""
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: dt.datetime


class SourceCreateIn(StrictModel):
    source_type: SourceType
    title: str = ""
    content: str = Field(min_length=1, max_length=MAX_SOURCE_SIZE)
    metadata: dict = Field(default_factory=dict)


class CollectionOut(StrictModel):
    id: int
    name: str
    description: str = ""
    sources: list[SourceOut]
    created_at: dt.datetime
    updated_at: dt.datetime


class CollectionCreateIn(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
