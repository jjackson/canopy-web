"""Pydantic schemas for /api/chat."""
from __future__ import annotations

import datetime as dt
import uuid

from ninja import Schema


class SessionCreateIn(Schema):
    agent_slug: str | None = None
    title: str = ""
    metadata: dict = {}


class SendIn(Schema):
    text: str


class MessageOut(Schema):
    turn_index: int
    role: str
    plaintext: str
    content: dict
    created_at: dt.datetime


class SessionOut(Schema):
    id: uuid.UUID
    agent_slug: str | None
    workspace: str
    title: str
    status: str
    created_at: dt.datetime


class SessionDetailOut(SessionOut):
    messages: list[MessageOut]


class SendOut(Schema):
    turn_id: uuid.UUID
    message: MessageOut
