"""Cron/timezone validation happens in the schema, so it 422s at the boundary."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.harness.schemas import ScheduleIn


def _payload(**over):
    base = dict(
        name="Weekly manager report", prompt="/echo:manager-report",
        cron="0 9 * * 5", timezone="America/New_York",
    )
    base.update(over)
    return base


def test_valid_payload():
    s = ScheduleIn(**_payload())
    assert s.cron == "0 9 * * 5"
    assert s.grace_minutes == 120
    assert s.notify == ["inbox"]


def test_bad_cron_rejected():
    with pytest.raises(ValidationError):
        ScheduleIn(**_payload(cron="every friday please"))


def test_bad_timezone_rejected():
    with pytest.raises(ValidationError):
        ScheduleIn(**_payload(timezone="Mars/Olympus_Mons"))


def test_blank_prompt_rejected():
    with pytest.raises(ValidationError):
        ScheduleIn(**_payload(prompt="   "))
