"""Django Ninja router for the /api/agents surface — a first-class AI-agent
workspace (agents, their Google-Doc syncs, work products, and skill catalog)."""
from __future__ import annotations

from django.http import HttpRequest
from ninja import Router, Status
from ninja.errors import HttpError

from apps.api.auth import session_auth
from apps.api.pagination import Page, paginate

from . import services
from .schemas import (
    AgentDetailOut,
    AgentIn,
    AgentOut,
    AgentSkillCatalogIn,
    AgentSkillOut,
    AgentSyncIn,
    AgentSyncOut,
    AgentTaskOut,
    AgentTaskSyncIn,
    AgentWorkProductBatchIn,
    AgentWorkProductOut,
    CountOut,
)

router = Router(auth=session_auth, tags=["agents"])


def _get_agent_or_404(slug: str):
    agent = services.get_agent(slug)
    if agent is None:
        raise HttpError(404, f"agent '{slug}' not found")
    return agent


@router.get("/", response=Page[AgentOut], summary="List agents",
            openapi_extra={"x-mcp-expose": True})
def list_agents(request: HttpRequest, limit: int = 100) -> Page[AgentOut]:
    limit = min(limit, 500)
    items = [AgentOut.model_validate(a) for a in services.list_agents()]
    return paginate(items, offset=0, limit=limit)


@router.post("/", response={201: AgentOut}, summary="Create or update an agent (upsert by slug)",
             openapi_extra={"x-mcp-expose": True})
def upsert_agent(request: HttpRequest, payload: AgentIn) -> Status:
    agent = services.upsert_agent(payload)
    return Status(201, AgentOut.model_validate(agent))


@router.get("/{slug}/", response=AgentDetailOut, summary="Agent detail (with counts)",
            openapi_extra={"x-mcp-expose": True})
def get_agent(request: HttpRequest, slug: str) -> AgentDetailOut:
    agent = _get_agent_or_404(slug)
    return AgentDetailOut.model_validate(services.agent_detail(agent))


# ---- syncs (Google-Doc backed) ----
@router.get("/{slug}/syncs/", response=Page[AgentSyncOut], summary="List the agent's syncs",
            openapi_extra={"x-mcp-expose": True})
def list_syncs(request: HttpRequest, slug: str, limit: int = 100) -> Page[AgentSyncOut]:
    limit = min(limit, 500)
    agent = _get_agent_or_404(slug)
    items = [AgentSyncOut.model_validate(s) for s in services.list_syncs(agent, limit=limit)]
    return paginate(items, offset=0, limit=limit)


@router.post("/{slug}/syncs/", response={201: AgentSyncOut},
             summary="Post a Google-Doc sync (idempotent per period+source)",
             openapi_extra={"x-mcp-expose": True})
def create_sync(request: HttpRequest, slug: str, payload: AgentSyncIn) -> Status:
    agent = _get_agent_or_404(slug)
    sync = services.upsert_sync(agent, payload)
    return Status(201, AgentSyncOut.model_validate(sync))


# ---- work products ----
@router.get("/{slug}/work-products/", response=Page[AgentWorkProductOut],
            summary="List the agent's work products",
            openapi_extra={"x-mcp-expose": True})
def list_work_products(request: HttpRequest, slug: str, limit: int = 200) -> Page[AgentWorkProductOut]:
    limit = min(limit, 500)
    agent = _get_agent_or_404(slug)
    items = [AgentWorkProductOut.model_validate(w) for w in services.list_work_products(agent, limit=limit)]
    return paginate(items, offset=0, limit=limit)


@router.post("/{slug}/work-products/", response=CountOut,
             summary="Add/update work products (upsert by url)",
             openapi_extra={"x-mcp-expose": True})
def add_work_products(request: HttpRequest, slug: str, payload: AgentWorkProductBatchIn) -> CountOut:
    agent = _get_agent_or_404(slug)
    result = services.upsert_work_products(agent, payload.work_products)
    return CountOut(**result)


# ---- skill catalog ----
@router.get("/{slug}/skills/", response=list[AgentSkillOut], summary="List the agent's skill catalog",
            openapi_extra={"x-mcp-expose": True})
def list_skills(request: HttpRequest, slug: str) -> list[AgentSkillOut]:
    agent = _get_agent_or_404(slug)
    return [AgentSkillOut.model_validate(s) for s in services.list_skills(agent)]


@router.put("/{slug}/skills/", response=CountOut, summary="Replace the agent's skill catalog",
            openapi_extra={"x-mcp-expose": True})
def replace_skills(request: HttpRequest, slug: str, payload: AgentSkillCatalogIn) -> CountOut:
    agent = _get_agent_or_404(slug)
    count = services.replace_skills(agent, payload.skills)
    return CountOut(count=count)


# ---- tasks (board) ----
@router.get("/{slug}/tasks/", response=list[AgentTaskOut], summary="List the agent's tasks (board)",
            openapi_extra={"x-mcp-expose": True})
def list_tasks(request: HttpRequest, slug: str) -> list[AgentTaskOut]:
    agent = _get_agent_or_404(slug)
    return [AgentTaskOut.model_validate(t) for t in services.list_tasks(agent)]


@router.post("/{slug}/tasks/sync", response=CountOut,
             summary="Sync (replace) the agent's task board from the source sheet",
             openapi_extra={"x-mcp-expose": True})
def sync_tasks(request: HttpRequest, slug: str, payload: AgentTaskSyncIn) -> CountOut:
    agent = _get_agent_or_404(slug)
    return CountOut(**services.sync_tasks(agent, payload.tasks))
