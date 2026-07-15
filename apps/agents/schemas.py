"""Pydantic schemas for the /api/agents surface."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from apps.common.schemas import StrictModel


# ---- Agent ----
class AgentIn(StrictModel):
    """Create or update an agent (upsert by slug)."""

    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    persona: str = ""
    email: str = Field(default="", max_length=254)
    avatar_url: str = Field(default="", max_length=500)
    # Optional explicit home: a workspace slug. Setting it on an already-homed
    # agent MOVES it (caller must be a member of the target). Empty → legacy
    # behavior (default workspace for unhomed agents).
    workspace: str = Field(default="", max_length=64)


class AgentOut(StrictModel):
    id: int
    slug: str
    name: str
    description: str
    persona: str
    email: str
    avatar_url: str
    created_at: dt.datetime
    updated_at: dt.datetime
    # The tenant that owns this agent — the fleet legitimately spans workspaces
    # (a chief-of-staff agent can live in a different tenant than the product
    # agents), so clients need this to build the correct deep link
    # (/w/<workspace>/agents/<slug>) instead of assuming the active workspace,
    # which 404s for cross-workspace agents (see commit 483c821).
    #
    # Aliased onto `workspace_id` rather than plain attribute resolution:
    # `Agent.workspace` is a FK, so a naive `obj.workspace` getattr would
    # dereference the related Workspace row (an extra query per agent) and
    # then fail str validation on the object itself. Workspace's primary key
    # IS its slug (apps/workspaces/models.py:29), so `agent.workspace_id` is
    # already the slug string with zero extra queries. Nullable for migration
    # safety, same as the FK itself.
    workspace: str | None = Field(default=None, validation_alias="workspace_id")


class AgentDetailOut(AgentOut):
    sync_count: int = 0
    work_product_count: int = 0
    skill_count: int = 0
    task_count: int = 0
    turn_count: int = 0
    latest_sync_at: dt.datetime | None = None
    latest_turn_at: dt.datetime | None = None


# ---- Sync (Google-Doc backed) ----
class AgentSyncIn(StrictModel):
    period_start: dt.datetime
    period_end: dt.datetime
    title: str = Field(min_length=1, max_length=200)
    summary: str = ""
    doc_url: str = Field(min_length=1, max_length=500)
    self_grades: dict[str, str] = Field(default_factory=dict)
    source: str = Field(min_length=1, max_length=100)


class AgentSyncOut(StrictModel):
    id: int
    agent_slug: str
    period_start: dt.datetime
    period_end: dt.datetime
    title: str
    summary: str
    doc_url: str
    self_grades: dict[str, str] = Field(default_factory=dict)
    source: str
    created_at: dt.datetime


# ---- Turns (a packaged unit of work + optional transcript link) ----
class AgentTurnIn(StrictModel):
    cli_session_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    summary: str = ""
    task_ext_ids: list[str] = Field(default_factory=list)
    work_product_urls: list[str] = Field(default_factory=list)
    session_slug: str = Field(default="", max_length=64)
    share_token: str = Field(default="", max_length=64)
    started_at: dt.datetime | None = None
    ended_at: dt.datetime | None = None
    source: str = Field(default="", max_length=100)


class AgentTurnOut(StrictModel):
    id: int
    agent_slug: str
    cli_session_id: str
    title: str
    summary: str
    task_ext_ids: list[str] = Field(default_factory=list)
    work_product_urls: list[str] = Field(default_factory=list)
    session_slug: str
    share_token: str
    started_at: dt.datetime | None = None
    ended_at: dt.datetime | None = None
    source: str
    created_at: dt.datetime


# ---- Work products ----
class AgentWorkProductIn(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="", max_length=40)
    url: str = Field(min_length=1, max_length=500)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="", max_length=100)


class AgentWorkProductBatchIn(StrictModel):
    work_products: list[AgentWorkProductIn] = Field(min_length=1)


class AgentWorkProductOut(StrictModel):
    id: int
    agent_slug: str
    title: str
    kind: str
    url: str
    description: str
    tags: list[str] = Field(default_factory=list)
    source: str
    created_at: dt.datetime


# ---- Skill catalog ----
class AgentSkillIn(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    url: str = Field(default="", max_length=500)
    improvement_note: str = ""


class AgentSkillCatalogIn(StrictModel):
    """Full replacement of the agent's skill catalog."""

    skills: list[AgentSkillIn] = Field(default_factory=list)


class AgentSkillOut(StrictModel):
    id: int
    agent_slug: str
    name: str
    description: str
    url: str
    improvement_note: str
    updated_at: dt.datetime


# ---- tasks (source: a Google Sheet; rendered as a board) ----
class AgentTaskLink(StrictModel):
    label: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=500)


class AgentTaskIn(StrictModel):
    ext_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    next_action: str = Field(default="", max_length=300)
    status: str = "suggested"  # normalized server-side
    owner: str = Field(default="", max_length=120)
    assigned: str = Field(default="", max_length=120)
    confidence: str = Field(default="", max_length=10)
    rationale: str = ""
    source_url: str = Field(default="", max_length=500)
    plan: str = ""
    due: dt.date | None = None
    links: list[AgentTaskLink] = Field(default_factory=list)
    notes: str = ""
    position: int = 0
    source: str = Field(default="", max_length=100)


class AgentTaskSyncIn(StrictModel):
    """Full replacement of the agent's task board from the source sheet."""

    tasks: list[AgentTaskIn] = Field(default_factory=list)


class AgentTaskOut(StrictModel):
    id: int
    agent_slug: str
    ext_id: str
    title: str
    next_action: str
    status: Literal["suggested", "in_progress", "done", "declined"]
    owner: str
    assigned: str
    confidence: str
    rationale: str
    source_url: str
    plan: str
    due: dt.date | None = None
    links: list[AgentTaskLink] = Field(default_factory=list)
    notes: str
    position: int
    updated_at: dt.datetime


class AgentTaskPatch(StrictModel):
    """Partial update — only the fields sent are written."""

    title: str | None = Field(default=None, max_length=300)
    next_action: str | None = Field(default=None, max_length=300)
    status: str | None = None
    owner: str | None = Field(default=None, max_length=120)
    assigned: str | None = Field(default=None, max_length=120)
    confidence: str | None = Field(default=None, max_length=10)
    rationale: str | None = None
    source_url: str | None = Field(default=None, max_length=500)
    plan: str | None = None
    due: dt.date | None = None
    notes: str | None = None
    position: int | None = None
    links: list[AgentTaskLink] | None = None


# ---- task commands (the board's action queue) ----
class AgentTaskCommandIn(StrictModel):
    kind: Literal["accept", "decline", "dispatch", "reassign", "edit", "comment", "done"]
    payload: dict = Field(default_factory=dict)  # reason / assignee / next_action / note
    created_by: str = Field(default="", max_length=200)


class AgentCommandApplyIn(StrictModel):
    result_note: str = ""


class AgentTaskCommandOut(StrictModel):
    id: int
    agent_slug: str
    task_id: int | None = None
    task_ext_id: str
    task_title: str
    kind: str
    payload: dict = Field(default_factory=dict)
    status: str
    created_by: str
    result_note: str
    created_at: dt.datetime
    applied_at: dt.datetime | None = None


class CommandResultOut(StrictModel):
    """Returned when the UI posts a command: the queued command + the (maybe
    immediately-updated) task."""

    command: AgentTaskCommandOut
    task: AgentTaskOut | None = None


# ---- "Needs you" supervisor inbox ----
class NeedsYouItem(StrictModel):
    type: Literal["review", "question", "notify"]
    # 'run' covers gate/step/completion items projected from the run lifecycle
    # (services._run_inbox_items) — task/sync/work_product are the board items.
    # 'schedule' is the unattended-occurrence nag (apps/harness) projected in via
    # needs_you(); it MUST stay in this Literal or the nag 500s at serialization.
    ref_kind: Literal["task", "sync", "work_product", "run", "schedule"]
    ref_id: int
    title: str
    subtitle: str = ""
    url: str = ""
    created_at: dt.datetime


class NeedsYouOut(StrictModel):
    agent_slug: str
    waiting_count: int  # gated (review + question) items — the "N waiting on you" badge
    items: list[NeedsYouItem] = Field(default_factory=list)


class FleetNeedsYouOut(StrictModel):
    """Every agent's needs-you in one response — the supervisor's home screen.
    One round trip instead of an N+1 fan-out, which matters on cellular."""

    total_waiting: int  # sum of per-agent waiting_count — the app-icon badge
    agents: list[NeedsYouOut] = Field(default_factory=list)


# ---- shared ----
class CountOut(StrictModel):
    created: int = 0
    replaced: int = 0
    count: int = 0
