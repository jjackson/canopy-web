"""The nag: an unfinished scheduled occurrence projects into needs_you."""
from __future__ import annotations

import datetime as dt

import pytest

from apps.agents import services as asvc
from apps.agents.models import Agent
from apps.harness import services as hsvc
from apps.harness.models import AgentSchedule, Turn

pytestmark = pytest.mark.django_db

SLOT = dt.datetime(2026, 7, 17, 13, tzinfo=dt.UTC)


def _executing(turn: Turn) -> Turn:
    """Drive a fired (QUEUED) turn into the state a runner's claim leaves it in.

    finish_turn is deliberately a no-op on a QUEUED turn — a runner must never
    finish a turn it never claimed (see services.finish_turn). Without this step
    a test's finish_turn silently does nothing and the turn stays QUEUED, which
    makes 'finished clears the nag' fail and 'missed still nags' pass for the
    wrong reason. Same idiom as tests/test_schedule_services.py.
    """
    Turn.objects.filter(pk=turn.pk).update(status=Turn.RUNNING)
    turn.refresh_from_db()
    return turn


@pytest.fixture()
def agent():
    return Agent.objects.create(slug="eva", name="Eva")


@pytest.fixture()
def schedule(agent):
    return AgentSchedule.objects.create(
        agent=agent, name="Goal review", prompt="/eva:goal-review",
        cron="0 9 1 * *", timezone="America/New_York",
    )


def test_never_fired_schedule_does_not_nag(agent, schedule):
    out = asvc.needs_you(agent)
    assert out["waiting_count"] == 0


def test_unfinished_occurrence_nags(agent, schedule):
    hsvc.fire_schedule(schedule, SLOT)

    out = asvc.needs_you(agent)

    items = [i for i in out["items"] if i["ref_kind"] == "schedule"]
    assert len(items) == 1
    assert items[0]["type"] == "review"
    assert items[0]["ref_id"] == schedule.id
    assert items[0]["title"] == "Goal review"
    assert out["waiting_count"] == 1  # counts toward the 'N waiting on you' badge


def test_finished_occurrence_clears_the_nag(agent, schedule):
    turn, _ = hsvc.fire_schedule(schedule, SLOT)
    hsvc.finish_turn(_executing(turn), status=Turn.DONE)

    out = asvc.needs_you(agent)

    assert [i for i in out["items"] if i["ref_kind"] == "schedule"] == []
    assert out["waiting_count"] == 0


def test_missed_occurrence_still_nags_until_superseded(agent, schedule):
    """Released-as-missed is not done: you still owe it until the next slot."""
    turn, _ = hsvc.fire_schedule(schedule, SLOT)
    turn = hsvc.finish_turn(_executing(turn), status=Turn.MISSED, result_note="released")
    assert turn.status == Turn.MISSED  # guard: prove we nag on MISSED, not on QUEUED

    out = asvc.needs_you(agent)

    assert len([i for i in out["items"] if i["ref_kind"] == "schedule"]) == 1


def test_disabled_schedule_does_not_nag(agent, schedule):
    hsvc.fire_schedule(schedule, SLOT)
    schedule.enabled = False
    schedule.save()

    assert asvc.needs_you(agent)["waiting_count"] == 0
