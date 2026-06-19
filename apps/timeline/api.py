"""GET /api/timeline/ — one merged, filterable, team-wide activity feed.

Read-only aggregator over every subsystem (see :mod:`apps.timeline.sources`).
Session-authed like the rest of /api/; since "private" means "dimagi-only" (the
whole app is OAuth-gated), every authenticated user sees the full team feed —
no owner filtering.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from django.http import HttpRequest
from ninja import Router

from apps.api.auth import session_auth

from . import sources
from .schemas import ActivityEventOut, SubsystemOut, TimelineOut

router = Router(auth=session_auth, tags=["timeline"])

_MAX_LIMIT = 200
_DEFAULT_LIMIT = 50


@router.get("/", response=TimelineOut, summary="Team activity timeline")
def list_timeline(
    request: HttpRequest,
    subsystem: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    before: dt.datetime | None = None,
) -> TimelineOut:
    """Recent activity across all subsystems, newest first.

    - ``subsystem``: restrict to one filter key (unknown keys → all).
    - ``limit``: page size, clamped to 1..200.
    - ``before``: cursor — return only events older than this timestamp.
    """
    limit = max(1, min(limit, _MAX_LIMIT))
    sub = sources.valid_subsystem(subsystem)
    events = sources.gather(subsystem=sub, limit=limit, before=before, user=request.user)
    # A full page means there may be more; the tail's timestamp is the next cursor.
    next_before = events[-1].at if len(events) == limit else None
    return TimelineOut(
        events=[ActivityEventOut(**dataclasses.asdict(e)) for e in events],
        subsystems=[SubsystemOut(**s) for s in sources.subsystem_catalog()],
        next_before=next_before,
    )
