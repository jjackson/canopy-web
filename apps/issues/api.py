"""Django Ninja router for canopy.origin issue records — /api/issues/.

Upsert (idempotent re-sync), list, retrieve, and DELETE (for cleanup). Keyed by `repo` + `number`;
the repo's slash is `__`-escaped in path params (`jjackson/canopy` -> `jjackson__canopy`).
"""
from __future__ import annotations

from django.http import HttpRequest
from ninja import Router, Status

from apps.api.auth import session_auth
from apps.api.errors import TYPE_NOT_FOUND, ProblemError
from apps.api.pagination import Page, paginate

from .models import OriginIssue
from .schemas import OriginIssueIn, OriginIssueOut

router = Router(auth=session_auth, tags=["issues"])


def _out(obj: OriginIssue) -> OriginIssueOut:
    return OriginIssueOut.model_validate(obj)


def _unslug(repo_slug: str) -> str:
    return repo_slug.replace("__", "/")


def _get_or_404(repo_slug: str, number: int) -> OriginIssue:
    repo = _unslug(repo_slug)
    try:
        return OriginIssue.objects.get(repo=repo, number=number)
    except OriginIssue.DoesNotExist:
        raise ProblemError(
            404, "Issue record not found", type_=TYPE_NOT_FOUND,
            detail=f"No canopy.origin record for {repo}#{number}.",
        )


@router.post("/", response={200: OriginIssueOut, 201: OriginIssueOut}, summary="Upsert an origin record")
def upsert_issue(request: HttpRequest, payload: OriginIssueIn) -> Status:
    data = payload.model_dump()
    repo = data.pop("repo")
    number = data.pop("number")
    obj, created = OriginIssue.objects.update_or_create(repo=repo, number=number, defaults=data)
    return Status(201 if created else 200, _out(obj))


@router.get("/", response=Page[OriginIssueOut], summary="List origin records")
def list_issues(
    request: HttpRequest,
    initiative: str | None = None,
    repo: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> Page[OriginIssueOut]:
    qs = OriginIssue.objects.all()
    if initiative:
        qs = qs.filter(initiative=initiative)
    if repo:
        qs = qs.filter(repo=repo)
    return paginate([_out(o) for o in qs], offset=offset, limit=limit)


@router.get("/{repo_slug}/{number}/", response=OriginIssueOut, summary="Get an origin record")
def get_issue(request: HttpRequest, repo_slug: str, number: int) -> OriginIssueOut:
    return _out(_get_or_404(repo_slug, number))


@router.delete("/{repo_slug}/{number}/", response={204: None}, summary="Delete an origin record (cleanup)")
def delete_issue(request: HttpRequest, repo_slug: str, number: int) -> Status:
    _get_or_404(repo_slug, number).delete()
    return Status(204, None)
