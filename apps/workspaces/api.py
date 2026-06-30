"""Django Ninja router for /api/workspaces — the multi-tenancy surface.

Membership-scoped: a workspace is visible only to its members; a non-member
gets 404 (no existence leak). Creating a workspace makes the creator its owner.
Owners manage members + invites (RBAC via `_require_role`); invites are accepted
by token, only by the addressed email.
"""
from __future__ import annotations

import datetime as dt

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Status
from ninja.errors import HttpError

from apps.api.auth import session_auth

from .models import Workspace, WorkspaceInvite, WorkspaceMembership
from .schemas import (
    InviteCreateIn,
    InviteOut,
    MemberOut,
    WorkspaceCreateIn,
    WorkspaceOut,
)

router = Router(auth=session_auth, tags=["workspaces"])

INVITE_TTL_DAYS = 14


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


def _require_role(user, slug: str, *allowed: str) -> WorkspaceMembership:
    m = _membership_or_404(user, slug)  # 404 first — a non-member can't probe roles
    if m.role not in allowed:
        raise HttpError(403, f"requires one of roles {list(allowed)}")
    return m


def _invite_out(inv: WorkspaceInvite) -> InviteOut:
    return InviteOut(
        id=inv.id, email=inv.email, role=inv.role, token=inv.token,
        expires_at=inv.expires_at, accepted_at=inv.accepted_at, revoked_at=inv.revoked_at,
    )


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


# ---- members ----
@router.get("/{slug}/members/", response=list[MemberOut], summary="List members (member-only)",
            openapi_extra={"x-mcp-expose": True})
def list_members(request: HttpRequest, slug: str) -> list[MemberOut]:
    _membership_or_404(request.user, slug)
    members = (
        WorkspaceMembership.objects.filter(workspace_id=slug)
        .select_related("user").order_by("joined_at")
    )
    return [
        MemberOut(user_id=m.user_id, email=m.user.email, role=m.role, joined_at=m.joined_at)
        for m in members
    ]


@router.delete("/{slug}/members/{user_id}/", response={204: None},
               summary="Remove a member (owner-only)", openapi_extra={"x-mcp-expose": True})
def remove_member(request: HttpRequest, slug: str, user_id: int):
    _require_role(request.user, slug, WorkspaceMembership.OWNER)
    try:
        m = WorkspaceMembership.objects.get(workspace_id=slug, user_id=user_id)
    except WorkspaceMembership.DoesNotExist:
        raise HttpError(404, "member not found")
    if m.role == WorkspaceMembership.OWNER and (
        WorkspaceMembership.objects.filter(
            workspace_id=slug, role=WorkspaceMembership.OWNER
        ).count() == 1
    ):
        raise HttpError(400, "cannot remove the last owner")
    m.delete()
    return Status(204, None)


# ---- invites ----
@router.post("/{slug}/invites/", response={201: InviteOut}, summary="Invite by email (owner-only)",
             openapi_extra={"x-mcp-expose": True})
def create_invite(request: HttpRequest, slug: str, payload: InviteCreateIn) -> Status:
    _require_role(request.user, slug, WorkspaceMembership.OWNER)
    inv = WorkspaceInvite.objects.create(
        workspace_id=slug, email=payload.email, role=payload.role,
        invited_by=request.user,
        expires_at=timezone.now() + dt.timedelta(days=INVITE_TTL_DAYS),
    )
    return Status(201, _invite_out(inv))


@router.get("/{slug}/invites/", response=list[InviteOut], summary="List invites (member-only)",
            openapi_extra={"x-mcp-expose": True})
def list_invites(request: HttpRequest, slug: str) -> list[InviteOut]:
    _membership_or_404(request.user, slug)
    return [_invite_out(i) for i in WorkspaceInvite.objects.filter(workspace_id=slug).order_by("-created_at")]


@router.post("/{slug}/invites/{invite_id}/revoke", response={204: None},
             summary="Revoke an invite (owner-only)", openapi_extra={"x-mcp-expose": True})
def revoke_invite(request: HttpRequest, slug: str, invite_id: int):
    _require_role(request.user, slug, WorkspaceMembership.OWNER)
    try:
        inv = WorkspaceInvite.objects.get(workspace_id=slug, id=invite_id)
    except WorkspaceInvite.DoesNotExist:
        raise HttpError(404, "invite not found")
    if inv.accepted_at is None and inv.revoked_at is None:
        inv.revoked_at = timezone.now()
        inv.save(update_fields=["revoked_at"])
    return Status(204, None)


@router.post("/invites/{token}/accept", response=WorkspaceOut,
             summary="Accept an invite by token", openapi_extra={"x-mcp-expose": True})
def accept_invite(request: HttpRequest, token: str) -> WorkspaceOut:
    try:
        inv = WorkspaceInvite.objects.select_related("workspace").get(token=token)
    except WorkspaceInvite.DoesNotExist:
        raise HttpError(404, "invite not found")
    if not inv.is_pending():
        raise HttpError(410, "invite is expired, revoked, or already accepted")
    if inv.email and (request.user.email or "").lower() != inv.email.lower():
        raise HttpError(403, "this invite is addressed to a different email")
    m, _ = WorkspaceMembership.objects.get_or_create(
        workspace=inv.workspace, user=request.user,
        defaults={"role": inv.role, "invited_by": inv.invited_by},
    )
    inv.accepted_at = timezone.now()
    inv.save(update_fields=["accepted_at"])
    return _out(inv.workspace, m.role)
