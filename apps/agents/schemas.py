"""Pydantic schemas for the /api/agents surface."""
from __future__ import annotations

import datetime as dt

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


class AgentDetailOut(AgentOut):
    sync_count: int = 0
    work_product_count: int = 0
    skill_count: int = 0
    task_count: int = 0
    latest_sync_at: dt.datetime | None = None


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
    status: str = "todo"  # normalized server-side to a board column
    priority: str = Field(default="", max_length=20)
    owner: str = Field(default="", max_length=120)
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
    status: str
    priority: str
    owner: str
    due: dt.date | None = None
    links: list[AgentTaskLink] = Field(default_factory=list)
    notes: str
    position: int
    updated_at: dt.datetime


# ---- shared ----
class CountOut(StrictModel):
    created: int = 0
    replaced: int = 0
    count: int = 0
