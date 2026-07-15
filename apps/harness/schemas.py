"""Pydantic schemas for the /api/harness surface."""
from __future__ import annotations

import datetime as dt
import uuid

from ninja import Schema
from pydantic import field_validator

from .cron import validate_cron, validate_timezone


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


class ScheduleIn(Schema):
    """Create payload. Cron + tz validate here so a bad expression 422s as
    problem+json at edit time — a typo that silently never fires is the worst
    failure mode a scheduler has."""

    name: str
    prompt: str
    cron: str
    timezone: str = "UTC"
    enabled: bool = True
    routing: str = "prefer_local"
    grace_minutes: int = 120
    notify: list[str] = ["inbox"]

    @field_validator("cron")
    @classmethod
    def _check_cron(cls, v: str) -> str:
        return validate_cron(v)

    @field_validator("timezone")
    @classmethod
    def _check_tz(cls, v: str) -> str:
        return validate_timezone(v)

    @field_validator("name", "prompt")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("must not be blank")
        return v.strip()


class SchedulePatch(Schema):
    """Partial update. Every field optional; the same validators apply to any
    field actually supplied."""

    name: str | None = None
    prompt: str | None = None
    cron: str | None = None
    timezone: str | None = None
    enabled: bool | None = None
    routing: str | None = None
    grace_minutes: int | None = None
    notify: list[str] | None = None

    @field_validator("cron")
    @classmethod
    def _check_cron(cls, v: str | None) -> str | None:
        return validate_cron(v) if v is not None else v

    @field_validator("timezone")
    @classmethod
    def _check_tz(cls, v: str | None) -> str | None:
        return validate_timezone(v) if v is not None else v


class ScheduleOut(Schema):
    id: int
    agent_slug: str
    name: str
    prompt: str
    cron: str
    timezone: str
    enabled: bool
    routing: str
    grace_minutes: int
    notify: list[str]
    last_slot: dt.datetime | None = None
    # The anchor the runner MUST pass as due_slot(after=...). Server-computed as
    # `last_slot or created_at` so the runner cannot get the fallback wrong.
    # Without it a fresh schedule (last_slot=None) fires once for the slot BEFORE
    # it existed — a schedule created Wednesday would immediately owe last
    # Friday's report. See the runner-side section.
    fire_after: dt.datetime
    next_runs: list[dt.datetime] = []
    last_status: str = ""
    created_at: dt.datetime
    updated_at: dt.datetime


class SchedulePreviewIn(Schema):
    """Preview a cron the user is still typing — no row exists yet."""

    cron: str
    timezone: str = "UTC"

    @field_validator("cron")
    @classmethod
    def _check_cron(cls, v: str) -> str:
        return validate_cron(v)

    @field_validator("timezone")
    @classmethod
    def _check_tz(cls, v: str) -> str:
        return validate_timezone(v)


class SchedulePreviewOut(Schema):
    next_runs: list[dt.datetime]


class ScheduleFireIn(Schema):
    """The runner's report that a slot came due. The server re-derives nothing —
    but the slot is only honored as an idempotency anchor, never as a claim of
    authority: tenant scoping gates the route."""

    slot: dt.datetime
