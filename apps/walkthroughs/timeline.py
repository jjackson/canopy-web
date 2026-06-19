"""Timeline source for standalone walkthrough uploads.

Walkthroughs tied to a DDD run (they carry a ``run_id``/``narrative_slug``) are
surfaced by the ``ddd`` source instead — this emits only one-off uploads so the
two subsystems don't double-count the same artifact.
"""
from __future__ import annotations

import datetime as dt

from django.db.models import Q

from .models import Walkthrough


def recent_events(*, limit: int, before: dt.datetime | None, user) -> list:
    from apps.timeline.types import ActivityEvent, actor_name, cursor_page, truncate

    qs = (
        Walkthrough.objects.filter(Q(run_id__isnull=True) | Q(run_id=""))
        .filter(Q(narrative_slug__isnull=True) | Q(narrative_slug=""))
        .select_related("owner")
        .order_by("-created_at")
    )
    return [
        ActivityEvent(
            subsystem="walkthroughs",
            kind="walkthrough",
            at=w.created_at,
            title=w.title,
            summary=truncate(w.description),
            project_slug=w.project_slug,
            actor=actor_name(w.owner),
            href=f"/w/{w.id}",
            id=f"walkthrough:{w.id}",
            icon="video" if w.kind == Walkthrough.KIND_VIDEO else "deck",
        )
        for w in cursor_page(qs, "created_at", before=before, limit=limit)
    ]
