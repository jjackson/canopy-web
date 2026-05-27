"""Pydantic schemas for the /api/v2/walkthroughs surface.

Mirror the field set from apps/walkthroughs/serializers.py — the
walkthroughs app shipped in PR #40 (2026-05-26) with DRF serializers
that this replaces.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import EmailStr, Field

from apps.common.schemas import StrictModel

WalkthroughKind = Literal["html", "video"]
WalkthroughVisibility = Literal["private", "link"]


class WalkthroughListItemOut(StrictModel):
    id: uuid.UUID
    title: str
    description: str = ""
    kind: WalkthroughKind
    project_slug: str | None = None
    visibility: WalkthroughVisibility
    owner_email: EmailStr
    size_bytes: int = Field(ge=0)
    duration_sec: int | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class WalkthroughDetailOut(WalkthroughListItemOut):
    """Detail view adds share_token (owner only), content_type, is_owner."""

    share_token: str | None = None
    content_type: str
    is_owner: bool


class WalkthroughUploadIn(StrictModel):
    """Form-encoded body of POST /walkthroughs/ (alongside the multipart file).

    Used to validate the non-file form fields; the actual file comes
    through Ninja's UploadedFile primitive on the handler.
    """

    title: str = ""
    kind: WalkthroughKind
    project_slug: str = ""
    description: str = ""
    visibility: WalkthroughVisibility = "private"


class WalkthroughPatchIn(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    project_slug: str | None = None  # may be set to null to detach
    visibility: WalkthroughVisibility | None = None


class WalkthroughRotateTokenOut(StrictModel):
    share_token: str
