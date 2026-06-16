"""Pydantic schemas for the /api/sessions and /api/share surfaces."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import EmailStr, Field

from apps.common.schemas import StrictModel

SessionVisibility = Literal["private", "link"]
MessageRole = Literal["user", "assistant", "system", "tool_use", "tool_result"]


class SessionListItemOut(StrictModel):
    slug: str
    title: str = ""
    project_slug: str | None = None
    visibility: SessionVisibility
    owner_email: EmailStr
    message_count: int = Field(ge=0)
    redaction_count: int = Field(ge=0)
    share_token: str | None = None  # active token, owner only
    is_owner: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class SessionMessageOut(StrictModel):
    turn_index: int
    role: MessageRole
    content: dict
    plaintext: str = ""


class SessionDetailOut(SessionListItemOut):
    messages: list[SessionMessageOut] = []


class SharedSessionOut(StrictModel):
    """Public, read-only payload for /api/share/{token}. No owner identity."""

    title: str = ""
    redaction_count: int = Field(ge=0)
    messages: list[SessionMessageOut] = []


class SessionUploadOut(StrictModel):
    """Result of POST /api/sessions/upload."""

    slug: str
    message_count: int = Field(ge=0)
    redaction_count: int = Field(ge=0)
    visibility: SessionVisibility
    share_token: str | None = None
    duplicate: bool = False


class SessionPatchIn(StrictModel):
    title: str | None = Field(default=None, max_length=500)
    project_slug: str | None = None
    visibility: SessionVisibility | None = None


class SessionRotateTokenOut(StrictModel):
    share_token: str
