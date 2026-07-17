"""Django Ninja router for canopy.origin issue records — /api/issues/.

Upsert (idempotent re-sync), list, retrieve, and DELETE (for cleanup). Keyed by `repo` + `number`;
the repo's slash is `__`-escaped in path params (`jjackson/canopy` -> `jjackson__canopy`).
"""
from __future__ import annotations

from django.db.models import Q
from django.http import HttpRequest
from ninja import Router, Status

from apps.agents.models import Agent
from apps.api.auth import session_auth
from apps.api.errors import TYPE_NOT_FOUND, ProblemError
from apps.api.pagination import Page, clamp_limit, clamp_offset, paginate
from apps.workspaces import services as wsvc

from .models import OriginIssue
from .schemas import OriginIssueIn, OriginIssueOut

router = Router(auth=session_auth, tags=["issues"])


def _out(obj: OriginIssue) -> OriginIssueOut:
    return OriginIssueOut.model_validate(obj)


def _unslug(repo_slug: str) -> str:
    return repo_slug.replace("__", "/")


def _visible(qs, request: HttpRequest):
    """Scope to the caller's workspaces (the hard tenant boundary); legacy
    null-workspace rows stay visible to any authenticated caller."""
    slugs = wsvc.request_workspace_slugs(request)
    return qs.filter(Q(workspace_id__in=slugs) | Q(workspace__isnull=True))


def _get_or_404(request: HttpRequest, repo_slug: str, number: int) -> OriginIssue:
    repo = _unslug(repo_slug)
    obj = _visible(OriginIssue.objects.filter(repo=repo, number=number), request).first()
    if obj is None:
        raise ProblemError(
            404, "Issue record not found", type_=TYPE_NOT_FOUND,
            detail=f"No canopy.origin record for {repo}#{number}.",
        )
    return obj


def _assign_workspace(request: HttpRequest, agent_slug: str):
    """An origin record belongs to its authoring agent's workspace when the caller
    is a member of it (agent-authored provenance); otherwise the caller's pinned /
    default workspace — so nobody files a record into a workspace they're not in."""
    slugs = wsvc.request_workspace_slugs(request)
    agent = Agent.objects.filter(slug=agent_slug).first()
    if agent and agent.workspace_id in slugs:
        return agent.workspace
    pinned = getattr(request, "workspace_slug", None)
    ws = (
        wsvc.Workspace.objects.filter(slug=pinned).first() if pinned else None
    ) or wsvc.ensure_default_workspace()
    if ws is not None and request.user.is_authenticated:
        wsvc.ensure_member(ws, request.user)
    return ws


@router.post("/", response={200: OriginIssueOut, 201: OriginIssueOut}, summary="Upsert an origin record")
def upsert_issue(request: HttpRequest, payload: OriginIssueIn) -> Status:
    data = payload.model_dump()
    repo = data.pop("repo")
    number = data.pop("number")

    # (repo, number) is globally unique — one origin record per GitHub issue. If a
    # record already exists in a workspace the caller isn't a member of, they must
    # not overwrite it: 404 (don't leak existence), same as read/delete.
    existing = OriginIssue.objects.filter(repo=repo, number=number).first()
    if existing and existing.workspace_id is not None and existing.workspace_id not in wsvc.request_workspace_slugs(request):
        raise ProblemError(
            404, "Issue record not found", type_=TYPE_NOT_FOUND,
            detail=f"No canopy.origin record for {repo}#{number}.",
        )

    defaults = dict(data)
    if existing is None:
        defaults["workspace"] = _assign_workspace(request, data.get("agent") or "")
    obj, created = OriginIssue.objects.update_or_create(repo=repo, number=number, defaults=defaults)
    return Status(201 if created else 200, _out(obj))


@router.get("/", response=Page[OriginIssueOut], summary="List origin records")
def list_issues(
    request: HttpRequest,
    initiative: str | None = None,
    repo: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> Page[OriginIssueOut]:
    offset, limit = clamp_offset(offset), clamp_limit(limit)
    qs = _visible(OriginIssue.objects.all(), request)
    if initiative:
        qs = qs.filter(initiative=initiative)
    if repo:
        qs = qs.filter(repo=repo)
    return paginate([_out(o) for o in qs], offset=offset, limit=limit)


@router.get("/{repo_slug}/{number}/", response=OriginIssueOut, summary="Get an origin record")
def get_issue(request: HttpRequest, repo_slug: str, number: int) -> OriginIssueOut:
    return _out(_get_or_404(request, repo_slug, number))


@router.delete("/{repo_slug}/{number}/", response={204: None}, summary="Delete an origin record (cleanup)")
def delete_issue(request: HttpRequest, repo_slug: str, number: int) -> Status:
    _get_or_404(request, repo_slug, number).delete()
    return Status(204, None)
