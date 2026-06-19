"""Timeline source for shared Claude Code sessions.

Link-visible sessions deep-link to the public ``/share/<token>`` viewer; private
(dimagi-only) sessions fall back to the ``/sessions`` list (there's no per-session
owner route).
"""
from __future__ import annotations

import datetime as dt

from .models import Session


def recent_events(*, limit: int, before: dt.datetime | None, user) -> list:
    from apps.timeline.types import ActivityEvent, actor_name

    qs = Session.objects.select_related("owner").order_by("-created_at")
    if before is not None:
        qs = qs.filter(created_at__lt=before)
    out: list[ActivityEvent] = []
    for s in qs[:limit]:
        href = "/sessions"
        if s.visibility == Session.VISIBILITY_LINK:
            token = s.active_token()
            if token is not None:
                href = f"/share/{token.token}"
        out.append(
            ActivityEvent(
                subsystem="sessions",
                kind="session",
                at=s.created_at,
                title=s.title or "(untitled session)",
                project_slug=s.project_slug,
                actor=actor_name(s.owner),
                href=href,
                id=f"session:{s.slug}",
                icon="session",
            )
        )
    return out
