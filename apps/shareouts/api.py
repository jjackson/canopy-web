"""Django Ninja router for the /api/shareouts surface."""
from __future__ import annotations

import datetime as dt

from django.http import HttpRequest
from ninja import Router, Status

from apps.api.auth import session_auth
from apps.api.pagination import Page, paginate

from . import services
from .schemas import (
    ShareoutBatchIn,
    ShareoutBatchOut,
    ShareoutOut,
    ShareoutsClearIn,
    ShareoutsClearOut,
)

router = Router(auth=session_auth, tags=["shareouts"])


@router.get(
    "/",
    response=Page[ShareoutOut],
    summary="List shareouts",
    openapi_extra={"x-mcp-expose": True},
)
def list_shareouts(
    request: HttpRequest,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    project: str | None = None,
    limit: int = 100,
) -> Page[ShareoutOut]:
    """List dated work briefings, newest period first. Filters AND-combine."""
    limit = min(limit, 500)
    rows = services.list_shareouts(
        date_from=date_from, date_to=date_to, project=project, limit=limit
    )
    items = [ShareoutOut.model_validate(row) for row in rows]
    return paginate(items, offset=0, limit=limit)


@router.post(
    "/",
    response={201: ShareoutBatchOut},
    summary="Create shareouts (batch, idempotent per period+source)",
    openapi_extra={"x-mcp-expose": True},
)
def create_shareouts(
    request: HttpRequest,
    payload: ShareoutBatchIn,
) -> Status:
    """Create a batch of briefings. Re-posting the same period from the same
    source replaces the prior rows (see services.upsert_shareouts)."""
    result = services.upsert_shareouts(payload.shareouts)
    return Status(201, ShareoutBatchOut(**result))


@router.post(
    "/clear/",
    response=ShareoutsClearOut,
    summary="Clear shareouts by source / project / date (AND-combined)",
    openapi_extra={"x-mcp-expose": True},
)
def clear_shareouts(
    request: HttpRequest,
    payload: ShareoutsClearIn,
) -> ShareoutsClearOut:
    """Delete shareouts matching the filters. An empty body clears all."""
    count = services.clear_shareouts(
        source=payload.source,
        project=payload.project,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )
    return ShareoutsClearOut(cleared=count)
