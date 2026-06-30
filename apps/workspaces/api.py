"""Django Ninja router for /api/workspaces — the multi-tenancy surface.

Membership-scoped: a workspace is visible only to its members; a non-member
gets 404 (no existence leak). Creating a workspace makes the creator its owner.
RBAC for member/invite management lands in a follow-up increment.
"""
from __future__ import annotations

from django.http import HttpRequest
from ninja import Router, Status
from ninja.errors import HttpError

from apps.api.auth import session_auth

from .models import Workspace, WorkspaceMembership
from .schemas import WorkspaceCreateIn, WorkspaceOut

router = Router(auth=session_auth, tags=["workspaces"])


def _out(ws: Workspace, role: str) -> WorkspaceOut:
    return WorkspaceOut(
        slug=ws.slug,
        display_name=ws.display_name,
        auto_join_domains=ws.auto_join_domains,
        role=role,
        created_at=ws.created_at,
    )


def _membership_or_404(user, slug: str) -> WorkspaceMembership:
    try:
        return WorkspaceMembership.objects.select_related("workspace").get(
            workspace_id=slug, user=user
        )
    except WorkspaceMembership.DoesNotExist:
        raise HttpError(404, f"workspace '{slug}' not found")


@router.post("/", response={201: WorkspaceOut}, summary="Create a workspace",
             openapi_extra={"x-mcp-expose": True})
def create_workspace(request: HttpRequest, payload: WorkspaceCreateIn) -> Status:
    if Workspace.objects.filter(slug=payload.slug).exists():
        raise HttpError(409, f"workspace '{payload.slug}' already exists")
    ws = Workspace.objects.create(
        slug=payload.slug,
        display_name=payload.display_name,
        created_by=request.user,
        auto_join_domains=payload.auto_join_domains,
    )
    WorkspaceMembership.objects.create(
        workspace=ws, user=request.user, role=WorkspaceMembership.OWNER
    )
    return Status(201, _out(ws, WorkspaceMembership.OWNER))


@router.get("/", response=list[WorkspaceOut], summary="List my workspaces",
            openapi_extra={"x-mcp-expose": True})
def list_workspaces(request: HttpRequest) -> list[WorkspaceOut]:
    memberships = (
        WorkspaceMembership.objects.filter(user=request.user)
        .select_related("workspace")
        .order_by("-workspace__created_at")
    )
    return [_out(m.workspace, m.role) for m in memberships]


@router.get("/{slug}/", response=WorkspaceOut, summary="Get a workspace (member-only)",
            openapi_extra={"x-mcp-expose": True})
def get_workspace(request: HttpRequest, slug: str) -> WorkspaceOut:
    m = _membership_or_404(request.user, slug)
    return _out(m.workspace, m.role)
