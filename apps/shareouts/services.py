"""Business logic for shareouts — kept out of the Ninja router so it's
unit-testable without HTTP."""
from __future__ import annotations

import datetime as dt

from apps.projects.models import Project

from .models import Shareout


def _resolve_project(slug: str | None) -> tuple[Project | None, bool]:
    """Return (project, ok). ok is False only when a non-null slug doesn't
    resolve — the caller skips those. A null slug is the roll-up (ok=True)."""
    if not slug:
        return None, True
    try:
        return Project.objects.get(slug=slug), True
    except Project.DoesNotExist:
        return None, False


def upsert_shareouts(items: list) -> dict:
    """Create shareouts, replacing prior rows in the same group.

    Idempotency group = (project, period_start, period_end, source). For each
    distinct group present in the incoming batch we delete pre-existing rows in
    that group once (counted as `replaced`) before creating the new ones, so
    re-running a period from the same source overwrites rather than duplicates.

    `items` is a list of ShareoutIn-like objects (anything with the attribute
    names). Items whose `project_slug` doesn't resolve are skipped.

    Returns {created, replaced, skipped}.
    """
    created = replaced = skipped = 0
    cleared_groups: set[tuple] = set()

    for item in items:
        project, ok = _resolve_project(item.project_slug)
        if not ok:
            skipped += 1
            continue

        group = (
            project.pk if project else None,
            item.period_start,
            item.period_end,
            item.source,
        )
        if group not in cleared_groups:
            existing = Shareout.objects.filter(
                project=project,
                period_start=item.period_start,
                period_end=item.period_end,
                source=item.source,
            )
            replaced += existing.count()
            existing.delete()
            cleared_groups.add(group)

        Shareout.objects.create(
            project=project,
            period_start=item.period_start,
            period_end=item.period_end,
            title=item.title,
            summary=item.summary,
            content=item.content,
            links=[link.model_dump() for link in item.links],
            author=item.author,
            source=item.source,
        )
        created += 1

    return {"created": created, "replaced": replaced, "skipped": skipped}


def list_shareouts(
    *,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    project: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return up to `limit` shareouts (newest period first) as dicts shaped
    for ShareoutOut. Filters AND-combine.

    - date_from: period_end >= date_from
    - date_to:   period_start <= date_to
    - project:   project slug exact match (does not include roll-ups)
    """
    limit = min(max(limit, 0), 500)
    qs = Shareout.objects.select_related("project").all()
    if date_from is not None:
        qs = qs.filter(period_end__gte=date_from)
    if date_to is not None:
        qs = qs.filter(period_start__lte=date_to)
    if project:
        qs = qs.filter(project__slug=project)

    return [
        {
            "id": s.pk,
            "project_slug": s.project.slug if s.project_id else None,
            "project_name": s.project.name if s.project_id else None,
            "period_start": s.period_start,
            "period_end": s.period_end,
            "title": s.title,
            "summary": s.summary,
            "content": s.content,
            "links": s.links or [],
            "author": s.author,
            "source": s.source,
            "created_at": s.created_at,
        }
        for s in qs[:limit]
    ]
