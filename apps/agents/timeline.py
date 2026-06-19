"""Timeline source for the agents subsystem.

Three ``kind``s merge under ``agents``: ``sync`` (a periodic manager sync),
``work_product`` (a deliverable — links off-site to the doc/form), and ``task``
(a board task as it first appears).
"""
from __future__ import annotations

import datetime as dt

from .models import AgentSync, AgentTask, AgentWorkProduct


def recent_events(*, limit: int, before: dt.datetime | None, user) -> list:
    from apps.timeline.types import ActivityEvent, truncate

    events: list[ActivityEvent] = []

    syncs = AgentSync.objects.select_related("agent").order_by("-period_end")
    if before is not None:
        syncs = syncs.filter(period_end__lt=before)
    for s in syncs[:limit]:
        events.append(
            ActivityEvent(
                subsystem="agents",
                kind="sync",
                at=s.period_end,
                title=f"{s.agent.name}: {s.title}",
                summary=truncate(s.summary),
                href=f"/agents/{s.agent.slug}/syncs",
                id=f"sync:{s.id}",
                icon="sync",
            )
        )

    wps = AgentWorkProduct.objects.select_related("agent").order_by("-created_at")
    if before is not None:
        wps = wps.filter(created_at__lt=before)
    for w in wps[:limit]:
        events.append(
            ActivityEvent(
                subsystem="agents",
                kind="work_product",
                at=w.created_at,
                title=f"{w.agent.name}: {w.title}",
                summary=w.kind or None,
                href=w.url,
                external=True,
                id=f"workproduct:{w.id}",
                icon="doc",
            )
        )

    tasks = AgentTask.objects.select_related("agent").order_by("-created_at")
    if before is not None:
        tasks = tasks.filter(created_at__lt=before)
    for t in tasks[:limit]:
        events.append(
            ActivityEvent(
                subsystem="agents",
                kind="task",
                at=t.created_at,
                title=f"{t.agent.name}: {t.title}",
                summary=t.get_status_display(),
                href=f"/agents/{t.agent.slug}/tasks",
                id=f"task:{t.id}",
                icon="task",
            )
        )

    events.sort(key=lambda e: e.at, reverse=True)
    return events[:limit]
