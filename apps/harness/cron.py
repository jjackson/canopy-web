"""Slot math for AgentSchedule — cron parsing, validation, and due-slot lookup.

Pure functions, no Django models, so they are cheap to test exhaustively (DST is
the part that bites). All datetimes in and out are timezone-aware UTC; the local
wall-clock interpretation happens inside, against the schedule's IANA zone.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter


def validate_cron(expr: str) -> str:
    """Return `expr` unchanged, or raise ValueError. A cron typo that silently
    never fires is the worst failure mode a scheduler has — reject at edit time."""
    expr = (expr or "").strip()
    if not expr:
        raise ValueError("cron expression is required")
    if not croniter.is_valid(expr):
        raise ValueError(f"invalid cron expression: {expr!r}")
    return expr


def validate_timezone(name: str) -> str:
    """Return `name` unchanged, or raise ValueError if it is not an IANA zone."""
    name = (name or "").strip()
    if not name:
        raise ValueError("timezone is required")
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"invalid timezone: {name!r}") from exc
    return name


def due_slot(
    cron: str, tz: str, *, after: dt.datetime | None, now: dt.datetime
) -> dt.datetime | None:
    """The most recent slot strictly before `now` that is strictly after `after`.

    Both bounds are exclusive: croniter.get_prev() is strictly-before, so a slot
    landing exactly on `now` is not yet due — it is returned by the next call.

    Returns AT MOST ONE slot — never a backfill. Three weeks offline yields the
    newest occurrence only, which is the supersede rule applied at firing time:
    you only ever owe the latest goal review.
    """
    zone = ZoneInfo(validate_timezone(tz))
    local_now = now.astimezone(zone)
    # Walk backwards from now: the first previous fire time IS the newest slot.
    prev = croniter(validate_cron(cron), local_now).get_prev(dt.datetime)
    slot = prev.astimezone(dt.UTC)
    if after is not None and slot <= after:
        return None
    return slot


def next_slots(cron: str, tz: str, *, now: dt.datetime, count: int = 3) -> list[dt.datetime]:
    """The next `count` fire times after `now` — drives the UI's preview, which is
    what makes a raw cron expression trustworthy without a docs trip."""
    zone = ZoneInfo(validate_timezone(tz))
    itr = croniter(validate_cron(cron), now.astimezone(zone))
    return [itr.get_next(dt.datetime).astimezone(dt.UTC) for _ in range(count)]
