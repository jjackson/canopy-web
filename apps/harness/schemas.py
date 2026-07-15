"""Pydantic schemas for the /api/harness surface."""
from __future__ import annotations

import datetime as dt
import uuid

from ninja import Schema


class RunnerIn(Schema):
    name: str
    kind: str  # emdash|cloud|remote
    capabilities: dict = {}
    host: str = ""  # macOS user@hostname — load-bearing for session reuse across accounts
    workspace: str = ""  # tenant slug; defaults to the pairer's default workspace


class RunnerOut(Schema):
    id: uuid.UUID
    name: str
    kind: str
    status: str
    status_note: str
    last_heartbeat_at: dt.datetime | None
    capabilities: dict
    host: str
    workspace: str | None

    @staticmethod
    def resolve_workspace(obj) -> str | None:
        return obj.workspace_id


class HeartbeatIn(Schema):
    active_turn_ids: list[str] = []
    degraded: bool = False
    note: str = ""
    host: str = ""  # refresh the owning macOS host (in case a runner row is reused)


class ResolveSessionIn(Schema):
    agent_slug: str
    thread_key: str


class ResolveSessionOut(Schema):
    reuse: bool
    new_thread: bool
    emdash_task_id: str
    agent_task_ext_id: str
    summary: str
    link_id: str | None


class RecordSessionIn(Schema):
    agent_slug: str
    thread_key: str
    emdash_task_id: str = ""
    session_id: str = ""
    agent_task_ext_id: str | None = None
    summary: str | None = None


class TurnIn(Schema):
    agent_slug: str
    origin: str
    idempotency_key: str
    prompt: str = ""
    origin_ref: dict = {}
    routing: str = "prefer_local"


class TurnOut(Schema):
    id: uuid.UUID
    agent_slug: str
    origin: str
    status: str
    routing: str
    prompt: str
    origin_ref: dict
    claimed_by_name: str | None
    session_id: str
    result_note: str
    created_at: dt.datetime
    claimed_at: dt.datetime | None
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    lease_expires_at: dt.datetime | None

    @staticmethod
    def resolve_agent_slug(obj) -> str:
        return obj.agent.slug

    @staticmethod
    def resolve_claimed_by_name(obj) -> str | None:
        return obj.claimed_by.name if obj.claimed_by else None


class TurnEventIn(Schema):
    kind: str
    payload: dict = {}


class TurnEventsIn(Schema):
    events: list[TurnEventIn]


class TurnEventOut(Schema):
    seq: int
    ts: dt.datetime
    kind: str
    payload: dict


class TurnEventsOut(Schema):
    events: list[TurnEventOut]


class TurnEventCountOut(Schema):
    count: int


class TurnStartIn(Schema):
    session_id: str = ""


class TurnFinishIn(Schema):
    status: str  # done|failed
    result_note: str = ""
