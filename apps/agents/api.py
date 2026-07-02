"""Django Ninja router for the /api/agents surface — a first-class AI-agent
workspace (agents, their Google-Doc syncs, work products, and skill catalog)."""
from __future__ import annotations

from django.http import HttpRequest
from ninja import Router, Status
from ninja.errors import HttpError

from apps.api.auth import session_auth
from apps.api.pagination import Page, paginate
from apps.workspaces import services as wsvc

from . import services
from .schemas import (
    AgentDetailOut,
    AgentIn,
    AgentOut,
    AgentSkillCatalogIn,
    AgentSkillOut,
    AgentCommandApplyIn,
    AgentSyncIn,
    AgentSyncOut,
    AgentTaskCommandIn,
    AgentTaskCommandOut,
    AgentTaskIn,
    AgentTaskOut,
    AgentTaskPatch,
    AgentTaskSyncIn,
    AgentTurnIn,
    AgentTurnOut,
    AgentWorkProductBatchIn,
    AgentWorkProductOut,
    CommandResultOut,
    CountOut,
    NeedsYouOut,
)

router = Router(auth=session_auth, tags=["agents"])


def _get_agent_or_404(request: HttpRequest, slug: str):
    """Resolve an agent, gated by workspace membership. A non-member gets the
    same 404 as a missing agent (no existence leak). Domain users are auto-joined
    to the agent's workspace first, so the default-workspace case keeps working."""
    agent = services.get_agent(slug)
    if agent is None:
        raise HttpError(404, f"agent '{slug}' not found")
    wsvc.auto_join_workspaces(request.user)
    ws = getattr(request, "workspace_slug", None)
    if ws and agent.workspace_id != ws:
        raise HttpError(404, f"agent '{slug}' not found")  # wrong tenant
    if agent.workspace_id and not wsvc.is_member(request.user, agent.workspace_id):
        raise HttpError(404, f"agent '{slug}' not found")
    return agent


@router.get("/", response=Page[AgentOut], summary="List agents",
            openapi_extra={"x-mcp-expose": True})
def list_agents(request: HttpRequest, limit: int = 100) -> Page[AgentOut]:
    limit = min(limit, 500)
    wsvc.auto_join_workspaces(request.user)
    ws = getattr(request, "workspace_slug", None)
    slugs = {ws} if ws else wsvc.user_workspace_slugs(request.user)
    items = [
        AgentOut.model_validate(a)
        for a in services.list_agents()
        if a.workspace_id in slugs or (ws is None and a.workspace_id is None)
    ]
    return paginate(items, offset=0, limit=limit)


@router.post("/", response={201: AgentOut}, summary="Create or update an agent (upsert by slug)",
             openapi_extra={"x-mcp-expose": True})
def upsert_agent(request: HttpRequest, payload: AgentIn) -> Status:
    agent = services.upsert_agent(payload)
    # Scope to the request's workspace (from the /w/{ws} prefix or the compat
    # shim's default); fall back to the org default so an unchanged register()
    # (e.g. Echo's) keeps working.
    if agent.workspace_id is None:
        pinned = getattr(request, "workspace_slug", None)
        ws = (
            wsvc.Workspace.objects.filter(slug=pinned).first() if pinned else None
        ) or wsvc.ensure_default_workspace()
        if ws is not None:
            agent.workspace = ws
            agent.save(update_fields=["workspace"])
    if agent.workspace_id:
        wsvc.ensure_member(agent.workspace, request.user)  # creator keeps access
    return Status(201, AgentOut.model_validate(agent))


@router.get("/{slug}/", response=AgentDetailOut, summary="Agent detail (with counts)",
            openapi_extra={"x-mcp-expose": True})
def get_agent(request: HttpRequest, slug: str) -> AgentDetailOut:
    agent = _get_agent_or_404(request, slug)
    return AgentDetailOut.model_validate(services.agent_detail(agent))


@router.get("/{slug}/needs-you", response=NeedsYouOut,
            summary="What the human needs to act on — typed (review/question/notify) + ranked",
            openapi_extra={"x-mcp-expose": True})
def needs_you(request: HttpRequest, slug: str) -> NeedsYouOut:
    agent = _get_agent_or_404(request, slug)
    return NeedsYouOut.model_validate(services.needs_you(agent))


# ---- syncs (Google-Doc backed) ----
@router.get("/{slug}/syncs/", response=Page[AgentSyncOut], summary="List the agent's syncs",
            openapi_extra={"x-mcp-expose": True})
def list_syncs(request: HttpRequest, slug: str, limit: int = 100) -> Page[AgentSyncOut]:
    limit = min(limit, 500)
    agent = _get_agent_or_404(request, slug)
    items = [AgentSyncOut.model_validate(s) for s in services.list_syncs(agent, limit=limit)]
    return paginate(items, offset=0, limit=limit)


@router.post("/{slug}/syncs/", response={201: AgentSyncOut},
             summary="Post a Google-Doc sync (idempotent per period+source)",
             openapi_extra={"x-mcp-expose": True})
def create_sync(request: HttpRequest, slug: str, payload: AgentSyncIn) -> Status:
    agent = _get_agent_or_404(request, slug)
    sync = services.upsert_sync(agent, payload)
    return Status(201, AgentSyncOut.model_validate(sync))


# ---- turns (a packaged unit of work + optional transcript link) ----
@router.get("/{slug}/turns/", response=Page[AgentTurnOut], summary="List the agent's turns",
            openapi_extra={"x-mcp-expose": True})
def list_turns(request: HttpRequest, slug: str, limit: int = 100) -> Page[AgentTurnOut]:
    limit = min(limit, 500)
    agent = _get_agent_or_404(request, slug)
    items = [AgentTurnOut.model_validate(t) for t in services.list_turns(agent, limit=limit)]
    return paginate(items, offset=0, limit=limit)


@router.post("/{slug}/turns/", response={201: AgentTurnOut},
             summary="Package a turn (idempotent per cli_session_id)",
             openapi_extra={"x-mcp-expose": True})
def create_turn(request: HttpRequest, slug: str, payload: AgentTurnIn) -> Status:
    agent = _get_agent_or_404(request, slug)
    turn = services.upsert_turn(agent, payload)
    return Status(201, AgentTurnOut.model_validate(turn))


# ---- work products ----
@router.get("/{slug}/work-products/", response=Page[AgentWorkProductOut],
            summary="List the agent's work products",
            openapi_extra={"x-mcp-expose": True})
def list_work_products(request: HttpRequest, slug: str, limit: int = 200) -> Page[AgentWorkProductOut]:
    limit = min(limit, 500)
    agent = _get_agent_or_404(request, slug)
    items = [AgentWorkProductOut.model_validate(w) for w in services.list_work_products(agent, limit=limit)]
    return paginate(items, offset=0, limit=limit)


@router.post("/{slug}/work-products/", response=CountOut,
             summary="Add/update work products (upsert by url)",
             openapi_extra={"x-mcp-expose": True})
def add_work_products(request: HttpRequest, slug: str, payload: AgentWorkProductBatchIn) -> CountOut:
    agent = _get_agent_or_404(request, slug)
    result = services.upsert_work_products(agent, payload.work_products)
    return CountOut(**result)


# ---- skill catalog ----
@router.get("/{slug}/skills/", response=list[AgentSkillOut], summary="List the agent's skill catalog",
            openapi_extra={"x-mcp-expose": True})
def list_skills(request: HttpRequest, slug: str) -> list[AgentSkillOut]:
    agent = _get_agent_or_404(request, slug)
    return [AgentSkillOut.model_validate(s) for s in services.list_skills(agent)]


@router.put("/{slug}/skills/", response=CountOut, summary="Replace the agent's skill catalog",
            openapi_extra={"x-mcp-expose": True})
def replace_skills(request: HttpRequest, slug: str, payload: AgentSkillCatalogIn) -> CountOut:
    agent = _get_agent_or_404(request, slug)
    count = services.replace_skills(agent, payload.skills)
    return CountOut(count=count)


# ---- tasks (board) ----
@router.get("/{slug}/tasks/", response=list[AgentTaskOut], summary="List the agent's tasks (board)",
            openapi_extra={"x-mcp-expose": True})
def list_tasks(request: HttpRequest, slug: str) -> list[AgentTaskOut]:
    agent = _get_agent_or_404(request, slug)
    return [AgentTaskOut.model_validate(t) for t in services.list_tasks(agent)]


@router.post("/{slug}/tasks/sync", response=CountOut,
             summary="Upsert the agent's tasks from the (legacy) source sheet",
             openapi_extra={"x-mcp-expose": True})
def sync_tasks(request: HttpRequest, slug: str, payload: AgentTaskSyncIn) -> CountOut:
    agent = _get_agent_or_404(request, slug)
    return CountOut(**services.sync_tasks(agent, payload.tasks))


def _get_task_or_404(agent, task_id: int):
    task = services.get_task(agent, task_id)
    if task is None:
        raise HttpError(404, f"task {task_id} not found")
    return task


@router.post("/{slug}/tasks/", response={201: AgentTaskOut}, summary="Create a task",
             openapi_extra={"x-mcp-expose": True})
def create_task(request: HttpRequest, slug: str, payload: AgentTaskIn) -> Status:
    agent = _get_agent_or_404(request, slug)
    return Status(201, AgentTaskOut.model_validate(services.create_task(agent, payload)))


@router.patch("/{slug}/tasks/{task_id}/", response=AgentTaskOut, summary="Update a task",
              openapi_extra={"x-mcp-expose": True})
def patch_task(request: HttpRequest, slug: str, task_id: int, payload: AgentTaskPatch) -> AgentTaskOut:
    agent = _get_agent_or_404(request, slug)
    task = _get_task_or_404(agent, task_id)
    data = payload.model_dump(exclude_unset=True)
    return AgentTaskOut.model_validate(services.patch_task(task, data))


# ---- task commands (the board's action queue) ----
@router.post("/{slug}/tasks/{task_id}/commands", response={201: CommandResultOut},
             summary="Post a board action (accept/decline/dispatch/…) on a task",
             openapi_extra={"x-mcp-expose": True})
def post_command(request: HttpRequest, slug: str, task_id: int, payload: AgentTaskCommandIn) -> Status:
    agent = _get_agent_or_404(request, slug)
    task = _get_task_or_404(agent, task_id)
    created_by = payload.created_by or getattr(request.user, "email", "")
    cmd = services.create_command(agent, task, payload.kind, payload.payload, created_by)
    return Status(201, CommandResultOut(
        command=AgentTaskCommandOut.model_validate(cmd),
        task=AgentTaskOut.model_validate(cmd.task) if cmd.task_id else None,
    ))


@router.get("/{slug}/commands", response=list[AgentTaskCommandOut],
            summary="List commands (the agent reads ?status=pending)",
            openapi_extra={"x-mcp-expose": True})
def list_commands(request: HttpRequest, slug: str, status: str | None = None) -> list[AgentTaskCommandOut]:
    agent = _get_agent_or_404(request, slug)
    return [AgentTaskCommandOut.model_validate(c) for c in services.list_commands(agent, status)]


@router.post("/{slug}/commands/{cmd_id}/apply", response=AgentTaskCommandOut,
             summary="Mark a command applied (the agent calls this after acting)",
             openapi_extra={"x-mcp-expose": True})
def apply_command(request: HttpRequest, slug: str, cmd_id: int, payload: AgentCommandApplyIn) -> AgentTaskCommandOut:
    agent = _get_agent_or_404(request, slug)
    cmd = agent.commands.filter(id=cmd_id).select_related("task", "agent").first()
    if cmd is None:
        raise HttpError(404, f"command {cmd_id} not found")
    return AgentTaskCommandOut.model_validate(services.apply_command(cmd, payload.result_note))
