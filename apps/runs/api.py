"""Django Ninja v2 router for the DDD run views (read-only aggregation).

Mounted at ``/api/ddd``. A *narrative* is the run_id slug; runs roll up under
it. Everything here joins ``Walkthrough`` + ``ReviewRequest`` on ``run_id`` at
read time — see ``apps/runs/aggregate.py``. Team-internal: any authenticated
user (session or PAT) reads everything, same rule as the reviews dashboard.
"""
from __future__ import annotations

from django.http import HttpRequest
from ninja import Router, Status

from apps.api.auth import session_auth
from apps.api.errors import TYPE_NOT_FOUND, ProblemError

from . import aggregate, delete
from .schemas import NarrativeDetailOut, NarrativeListItemOut, RunPackageOut

router = Router(auth=session_auth, tags=["ddd"])


@router.get(
    "/narratives/",
    response=list[NarrativeListItemOut],
    summary="List DDD narratives",
)
def list_narratives(
    request: HttpRequest, project: str = "", mine: str = ""
) -> list[NarrativeListItemOut]:
    owner_id = (
        request.user.id if (mine == "true" and request.user.is_authenticated) else None
    )
    items = aggregate.list_narratives(
        project=project.strip() or None, owner_id=owner_id
    )
    return [NarrativeListItemOut.model_validate(it) for it in items]


@router.get(
    "/narratives/{slug}/",
    response=NarrativeDetailOut,
    summary="Get a narrative + its runs",
)
def get_narrative(request: HttpRequest, slug: str) -> NarrativeDetailOut:
    data = aggregate.build_narrative(slug)
    if data is None:
        raise ProblemError(404, "Narrative not found", type_=TYPE_NOT_FOUND)
    return NarrativeDetailOut.model_validate(data)


@router.get(
    "/runs/{run_id}/",
    response=RunPackageOut,
    summary="Get a run package (video + deck + narrative + links)",
)
def get_run(request: HttpRequest, run_id: str) -> RunPackageOut:
    data = aggregate.build_run(run_id)
    if data is None:
        raise ProblemError(404, "Run not found", type_=TYPE_NOT_FOUND)
    return RunPackageOut.model_validate(data)


# ---------------------------------------------------------------------------
# Cascade deletes
#
# Team-internal cleanup, same auth rule as the reviews dashboard: any
# authenticated user (session or PAT) may delete. Each delete cascades the
# rows that roll up under the target and best-effort removes rendered files
# from Drive — see ``apps/runs/delete.py``. 204 on success, 404 when nothing
# matched.
# ---------------------------------------------------------------------------


@router.delete(
    "/runs/{run_id}/",
    response={204: None},
    summary="Delete a run (its walkthroughs + reviews)",
)
def delete_run(request: HttpRequest, run_id: str):
    if delete.delete_run(run_id) is None:
        raise ProblemError(404, "Run not found", type_=TYPE_NOT_FOUND)
    return Status(204, None)


@router.delete(
    "/narratives/{slug}/versions/{version}/",
    response={204: None},
    summary="Delete a narrative version (and the runs under it)",
)
def delete_version(request: HttpRequest, slug: str, version: int):
    if delete.delete_version(slug, version) is None:
        raise ProblemError(404, "Narrative version not found", type_=TYPE_NOT_FOUND)
    return Status(204, None)


@router.delete(
    "/narratives/{slug}/",
    response={204: None},
    summary="Delete an entire narrative (all versions + runs)",
)
def delete_narrative(request: HttpRequest, slug: str):
    if delete.delete_narrative(slug) is None:
        raise ProblemError(404, "Narrative not found", type_=TYPE_NOT_FOUND)
    return Status(204, None)
