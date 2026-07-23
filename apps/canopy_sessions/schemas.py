"""Pydantic schemas for /api/canopy-sessions."""
from __future__ import annotations

import datetime as dt
import uuid

from ninja import Schema


class SessionCreateIn(Schema):
    agent_slug: str | None = None
    # An agentless PROJECT chat: the repo checkout to drive. Mutually exclusive
    # with agent_slug.
    project: str = ""
    title: str = ""
    metadata: dict = {}


class SendIn(Schema):
    text: str
    # Optional client-generated nonce for idempotent (double-submit-safe) sends.
    client_id: str = ""


class MessageOut(Schema):
    turn_index: int
    role: str
    plaintext: str
    content: dict
    created_at: dt.datetime


class MessagePageOut(Schema):
    """One backward page of transcript for scroll-back ("Load earlier")."""
    messages: list[MessageOut]
    has_more_before: bool


class SessionOut(Schema):
    id: uuid.UUID
    agent_slug: str | None
    project: str
    workspace: str
    title: str
    status: str
    created_at: dt.datetime
    # Liveness (Plan 4) — computed from the RunnerBinding; a web session with no
    # binding is origin="web", running=False, runner_name=None.
    origin: str = "web"
    running: bool = False
    runner_name: str | None = None
    runner_location: str | None = None
    session_key: str = ""


class SessionDetailOut(SessionOut):
    messages: list[MessageOut]
    # Tail-first cursor: the transcript ships the last N messages by default;
    # these tell the client whether earlier history exists and where the loaded
    # window starts, for scroll-back / "load full". See services.SESSION_TAIL_DEFAULT.
    has_more_before: bool = False
    oldest_loaded_turn_index: int | None = None


class SendOut(Schema):
    turn_id: uuid.UUID | None
    message: MessageOut


class StreamStateOut(Schema):
    """Whether the bound runner is being asked to stream this session live."""
    streaming: bool


class BackfillStateOut(Schema):
    """ready = already server-full; requested = runner asked; unavailable = offline."""
    status: str
