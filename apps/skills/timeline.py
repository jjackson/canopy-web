"""Timeline source for the skill catalog."""
from __future__ import annotations

import datetime as dt

from .models import Skill


def recent_events(*, limit: int, before: dt.datetime | None, user) -> list:
    from apps.timeline.types import ActivityEvent, cursor_page, truncate

    qs = Skill.objects.order_by("-created_at")
    return [
        ActivityEvent(
            subsystem="skills",
            kind="skill",
            at=sk.created_at,
            title=sk.name,
            summary=truncate(sk.description),
            href=f"/skills/{sk.id}",
            id=f"skill:{sk.id}",
            icon="skill",
        )
        for sk in cursor_page(qs, "created_at", before=before, limit=limit)
    ]
