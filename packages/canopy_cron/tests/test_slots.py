"""Slot math for AgentSchedule. No DB, no Django — pure functions."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from canopy_cron import due_slot, next_slots, validate_cron, validate_timezone

FRIDAYS_9AM = "0 9 * * 5"
NY = "America/New_York"


def _utc(y, m, d, h, mi=0) -> dt.datetime:
    return dt.datetime(y, m, d, h, mi, tzinfo=dt.UTC)


def test_validate_cron_accepts_and_rejects():
    assert validate_cron(FRIDAYS_9AM) == FRIDAYS_9AM
    with pytest.raises(ValueError):
        validate_cron("not a cron")
    with pytest.raises(ValueError):
        validate_cron("")


def test_validate_timezone_accepts_and_rejects():
    assert validate_timezone(NY) == NY
    with pytest.raises(ValueError):
        validate_timezone("Mars/Olympus_Mons")


def test_due_slot_none_before_first_fire():
    """A schedule anchored at creation owes nothing until its first real slot.

    2026-07-15 is a Wednesday and the next Friday 9am ET has not happened. Note the
    anchor is what makes this None: `due_slot` looks BACKWARD, and 2026-07-10 is
    itself a Friday, so an unanchored call would legitimately return it (see
    test_due_slot_unanchored_returns_the_previous_slot). Anchoring on the creation
    time is what stops a slot from before the schedule existed from firing.
    """
    created = _utc(2026, 7, 15, 11)
    assert due_slot(FRIDAYS_9AM, NY, after=created, now=_utc(2026, 7, 15, 12)) is None


def test_due_slot_unanchored_returns_the_previous_slot():
    """`after=None` has no lower bound, so the most recent past slot IS due.

    Pins the contract rather than leaving it accidental: callers that must not fire
    a pre-creation slot are responsible for passing an anchor. AgentSchedule.last_slot
    is nullable and starts None, so this path is reachable in production — see the
    task-3 report.
    """
    slot = due_slot(FRIDAYS_9AM, NY, after=None, now=_utc(2026, 7, 15, 12))
    assert slot == _utc(2026, 7, 10, 13)  # the previous Friday, 09:00 ET under EDT


def test_due_slot_returns_the_slot_once_passed():
    # Friday 2026-07-17 09:00 ET == 13:00 UTC (EDT, UTC-4).
    slot = due_slot(FRIDAYS_9AM, NY, after=None, now=_utc(2026, 7, 17, 14))
    assert slot == _utc(2026, 7, 17, 13)


def test_due_slot_respects_after_no_refire():
    slot = _utc(2026, 7, 17, 13)
    assert due_slot(FRIDAYS_9AM, NY, after=slot, now=_utc(2026, 7, 17, 14)) is None


def test_due_slot_never_backfills():
    """Three weeks offline yields ONE slot — the newest — not three."""
    slot = due_slot(FRIDAYS_9AM, NY, after=_utc(2026, 6, 26, 13), now=_utc(2026, 7, 17, 14))
    assert slot == _utc(2026, 7, 17, 13)  # newest, not 2026-07-03 or 2026-07-10


def test_due_slot_dst_holds_local_9am():
    """9am ET stays 9am across the DST shift: EDT=13:00Z, EST=14:00Z."""
    edt = due_slot(FRIDAYS_9AM, NY, after=None, now=_utc(2026, 10, 30, 20))
    assert edt == _utc(2026, 10, 30, 13)
    # 2026-11-06 is after the US shift back to EST (UTC-5).
    est = due_slot(FRIDAYS_9AM, NY, after=_utc(2026, 10, 30, 13), now=_utc(2026, 11, 6, 20))
    assert est == _utc(2026, 11, 6, 14)


def test_next_slots_previews_three():
    out = next_slots(FRIDAYS_9AM, NY, now=_utc(2026, 7, 15, 12), count=3)
    assert out == [_utc(2026, 7, 17, 13), _utc(2026, 7, 24, 13), _utc(2026, 7, 31, 13)]


def test_next_slots_dst_holds_local_9am_across_the_shift():
    """The preview must cross the DST boundary the way firing does.

    `next_slots` does its OWN zone conversion — it does not share a code path with
    `due_slot` — so `test_due_slot_dst_holds_local_9am` above pins nothing here, and
    every other `next_slots` case sits entirely inside EDT.

    The US shifts back to EST on Sunday 2026-11-01, so a window opened the Monday
    before spans it: 9am ET is 13:00Z under EDT (UTC-4) and 14:00Z under EST
    (UTC-5). The same cron expression must therefore yield two *different* UTC
    instants either side of the shift. Evaluating in UTC would emit a constant
    09:00Z; anchoring the whole window to the start offset would emit a constant
    13:00Z. Both are wrong, and both are invisible to a single-offset window.

    A bug here mislabels rather than misfires — but the preview is the only thing
    that makes a hand-typed cron trustworthy, so a wrong "Next" is a wrong schedule.
    """
    # 2026-10-26 is the Monday before the shift; the window covers Fridays either side.
    out = next_slots(FRIDAYS_9AM, NY, now=_utc(2026, 10, 26, 12), count=3)

    assert out == [
        _utc(2026, 10, 30, 13),  # Fri 09:00 EDT (UTC-4) — before the shift
        _utc(2026, 11, 6, 14),   # Fri 09:00 EST (UTC-5) — after it
        _utc(2026, 11, 13, 14),  # Fri 09:00 EST
    ]
    # The point of the window: the UTC instant moves precisely because the local
    # wall clock does not.
    assert out[1] - out[0] == dt.timedelta(days=7, hours=1)
    assert out[2] - out[1] == dt.timedelta(days=7)


def test_next_slots_are_always_9am_local_whatever_the_offset():
    """Restates the contract in the units the user actually set it in.

    The assertion above is in UTC and so encodes the offsets by hand; this one
    reads the wall clock back through the zone, and would fail on any zone-handling
    regression without anyone having to recompute an offset table.
    """
    zone = ZoneInfo(NY)
    out = next_slots(FRIDAYS_9AM, NY, now=_utc(2026, 10, 26, 12), count=6)

    local = [slot.astimezone(zone) for slot in out]
    assert {(t.hour, t.minute) for t in local} == {(9, 0)}
    assert {t.strftime("%A") for t in local} == {"Friday"}
    # the window genuinely straddles the shift, else this proves nothing
    assert {t.tzname() for t in local} == {"EDT", "EST"}
