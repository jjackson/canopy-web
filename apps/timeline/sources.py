"""Registry + merge for the team activity timeline.

Each entry points at a ``recent_events(*, limit, before, user)`` callable living
in a subsystem's own ``timeline.py``. The aggregator calls the enabled sources,
merges their events, sorts newest-first, and slices to ``limit``. A source that
raises is logged and skipped — one broken subsystem never blanks the whole feed.

No new tables: every source reads live models at request time. Each source
returns at most ``limit`` events (and only events older than ``before`` when a
cursor is given), so worst-case work is ``len(sources) * limit`` rows.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from importlib import import_module

from .types import ActivityEvent

logger = logging.getLogger(__name__)

#: (key, label, "module.path", "callable_name"). Order is the rail order.
_REGISTRY: list[tuple[str, str, str, str]] = [
    ("ddd", "DDD", "apps.runs.timeline", "recent_events"),
    ("insights", "Insights", "apps.projects.timeline", "insight_events"),
    ("walkthroughs", "Walkthroughs", "apps.walkthroughs.timeline", "recent_events"),
    ("shareouts", "Shareouts", "apps.shareouts.timeline", "recent_events"),
    ("agents", "Agents", "apps.agents.timeline", "recent_events"),
    ("sessions", "Sessions", "apps.sessions.timeline", "recent_events"),
    ("projects", "Projects", "apps.projects.timeline", "project_events"),
    ("skills", "Skills", "apps.skills.timeline", "recent_events"),
    ("workspace", "Workspace", "apps.workspace.timeline", "recent_events"),
]


def subsystem_catalog() -> list[dict[str, str]]:
    """[{key, label}] for the filter rail, in registry order."""
    return [{"key": key, "label": label} for key, label, _, _ in _REGISTRY]


def valid_subsystem(key: str | None) -> str | None:
    """Return ``key`` if it's a known subsystem, else ``None`` (→ all)."""
    known = {k for k, _, _, _ in _REGISTRY}
    return key if key in known else None


def _resolve(module_path: str, attr: str) -> Callable[..., list[ActivityEvent]]:
    return getattr(import_module(module_path), attr)


def gather(
    *,
    subsystem: str | None,
    limit: int,
    before: dt.datetime | None,
    user,
) -> list[ActivityEvent]:
    """Merged, newest-first events across the enabled sources, capped at ``limit``."""
    entries = [e for e in _REGISTRY if subsystem is None or e[0] == subsystem]
    events: list[ActivityEvent] = []
    for key, _label, module_path, attr in entries:
        try:
            fn = _resolve(module_path, attr)
            events.extend(fn(limit=limit, before=before, user=user) or [])
        except Exception:  # one bad source must not blank the feed
            logger.exception("timeline source %r failed", key)
    events.sort(key=lambda ev: ev.at, reverse=True)
    return events[:limit]
