"""Timeline source for the agents subsystem.

Three ``kind``s merge under ``agents``: ``sync`` (a periodic manager sync),
``work_product`` (a deliverable — links off-site to the doc/form), and ``task``
(a board task as it first appears).

Returns *candidates* (newest ``limit`` per component plus cursor-instant ties);
:func:`apps.timeline.sources.gather` does the final merge/order/slice.
"""
from __future__ import annotations

import datetime as dt

from .models import AgentSync, AgentTask, AgentWorkProduct


def recent_events(*, limit: int, before: dt.datetime | None, user) -> list:
    from apps.timeline.types import ActivityEvent, cursor_page, truncate

    events: list[ActivityEvent] = []

    syncs = AgentSync.objects.select_related("agent").order_by("-period_end")
    for s in cursor_page(syncs, "period_end", before=before, limit=limit):
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
    for w in cursor_page(wps, "created_at", before=before, limit=limit):
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
    for t in cursor_page(tasks, "created_at", before=before, limit=limit):
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

    return events
