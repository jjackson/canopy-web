"""Timeline sources for the projects app.

Two subsystems land here: ``insights`` (the cross-portfolio AI insight cards,
stored as ``ProjectContext`` rows with ``context_type="insight"``) and
``projects`` (the other context pushes + skill actions). They're separate filter
keys, so they're separate callables.

Each returns *candidates* (newest ``limit`` per component plus cursor-instant
ties); :func:`apps.timeline.sources.gather` does the final merge/order/slice.
"""
from __future__ import annotations

import datetime as dt

from .models import ProjectAction, ProjectContext


def insight_events(*, limit: int, before: dt.datetime | None, user) -> list:
    from apps.timeline.types import ActivityEvent, cursor_page, first_line

    qs = (
        ProjectContext.objects.filter(context_type="insight")
        .select_related("project")
        .order_by("-created_at")
    )
    return [
        ActivityEvent(
            subsystem="insights",
            kind="insight",
            at=c.created_at,
            title=first_line(c.content) or "Insight",
            summary=None,
            project_slug=c.project.slug,
            actor=c.source or None,
            href="/insights",
            id=f"insight:{c.id}",
            icon="insight",
        )
        for c in cursor_page(qs, "created_at", before=before, limit=limit)
    ]


def project_events(*, limit: int, before: dt.datetime | None, user) -> list:
    from apps.timeline.types import ActivityEvent, cursor_page, first_line

    events: list[ActivityEvent] = []

    ctx = (
        ProjectContext.objects.exclude(context_type="insight")
        .select_related("project")
        .order_by("-created_at")
    )
    for c in cursor_page(ctx, "created_at", before=before, limit=limit):
        label = dict(ProjectContext.CONTEXT_TYPES).get(c.context_type, c.context_type)
        events.append(
            ActivityEvent(
                subsystem="projects",
                kind="context",
                at=c.created_at,
                title=f"{label}: {first_line(c.content) or '—'}",
                project_slug=c.project.slug,
                actor=c.source or None,
                href="/",
                id=f"context:{c.id}",
                icon="note",
            )
        )

    acts = ProjectAction.objects.select_related("project").order_by("-started_at")
    for a in cursor_page(acts, "started_at", before=before, limit=limit):
        events.append(
            ActivityEvent(
                subsystem="projects",
                kind="action",
                at=a.started_at,
                title=f"{a.skill_name} · {a.status}",
                project_slug=a.project.slug,
                href="/",
                id=f"action:{a.id}",
                icon="skill",
            )
        )

    return events
