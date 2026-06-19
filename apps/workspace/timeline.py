"""Timeline source for workspace sessions (published skills)."""
from __future__ import annotations

import datetime as dt

from .models import WorkspaceSession


def recent_events(*, limit: int, before: dt.datetime | None, user) -> list:
    from apps.timeline.types import ActivityEvent, cursor_page

    qs = WorkspaceSession.objects.filter(status="published").order_by("-updated_at")
    out: list[ActivityEvent] = []
    for ws in cursor_page(qs, "updated_at", before=before, limit=limit):
        draft = ws.skill_draft if isinstance(ws.skill_draft, dict) else {}
        name = (draft.get("name") or "").strip() or "skill"
        out.append(
            ActivityEvent(
                subsystem="workspace",
                kind="workspace",
                at=ws.updated_at,
                title=f"Published: {name}",
                href=f"/workspace/{ws.id}",
                id=f"workspace:{ws.id}",
                icon="skill",
            )
        )
    return out
