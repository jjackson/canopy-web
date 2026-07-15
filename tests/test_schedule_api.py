"""API tests for /api/agents/{slug}/schedules — human CRUD + run-now."""
from __future__ import annotations

import datetime as dt

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.agents.models import Agent
from apps.harness.models import AgentSchedule, Turn

pytestmark = pytest.mark.django_db


@pytest.fixture()
def client():
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture()
def agent():
    return Agent.objects.create(slug="echo", name="Echo")


def _create(client, **over):
    body = {
        "name": "Weekly manager report", "prompt": "/echo:manager-report",
        "cron": "0 9 * * 5", "timezone": "America/New_York",
    }
    body.update(over)
    return client.post(
        "/api/agents/echo/schedules/", body, content_type="application/json"
    )


def test_create_and_list(client, agent):
    resp = _create(client)
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["agent_slug"] == "echo"
    assert body["cron"] == "0 9 * * 5"
    assert len(body["next_runs"]) == 3  # the UI preview

    listing = client.get("/api/agents/echo/schedules/")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


def test_bad_cron_is_422_problem_json(client, agent):
    resp = _create(client, cron="every friday please")
    assert resp.status_code == 422
    assert resp["content-type"] == "application/problem+json"


def test_patch_toggles_enabled(client, agent):
    sid = _create(client).json()["id"]
    resp = client.patch(
        f"/api/agents/echo/schedules/{sid}", {"enabled": False},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_patch_with_explicit_null_does_not_500(client, agent):
    """An explicit {"cron": null} must not setattr None onto a non-nullable
    column. SchedulePatch's validator short-circuits on None, so this can only
    be caught here."""
    sid = _create(client).json()["id"]
    resp = client.patch(
        f"/api/agents/echo/schedules/{sid}", {"cron": None},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["cron"] == "0 9 * * 5"  # unchanged, not nulled


def test_delete(client, agent):
    sid = _create(client).json()["id"]
    assert client.delete(f"/api/agents/echo/schedules/{sid}").status_code == 204
    assert AgentSchedule.objects.count() == 0


def test_run_now_enqueues_a_manual_turn(client, agent):
    sid = _create(client).json()["id"]
    resp = client.post(f"/api/agents/echo/schedules/{sid}/run-now")
    assert resp.status_code == 202, resp.content
    turn = Turn.objects.get()
    assert turn.origin == Turn.ORIGIN_MANUAL
    assert turn.prompt == "/echo:manager-report"


def test_unknown_agent_404s(client):
    assert client.get("/api/agents/nope/schedules/").status_code == 404


def test_fire_after_defaults_to_created_at_not_null(client, agent):
    """A fresh schedule must never fire for a slot that predates it.

    last_slot is NULL until the first fire, and due_slot(after=None) looks
    backward with no lower bound — so a schedule created Wednesday would
    immediately owe LAST Friday's report. fire_after is the server-computed
    anchor that closes that hole; the runner passes it straight to due_slot.
    """
    body = _create(client).json()
    schedule = AgentSchedule.objects.get(pk=body["id"])

    assert body["last_slot"] is None
    assert body["fire_after"] == schedule.created_at.isoformat().replace("+00:00", "Z")


def test_fire_after_tracks_last_slot_once_fired(client, agent):
    from apps.harness import services

    schedule = AgentSchedule.objects.get(pk=_create(client).json()["id"])
    slot = dt.datetime(2026, 7, 17, 13, tzinfo=dt.UTC)
    services.fire_schedule(schedule, slot)

    body = client.get("/api/agents/echo/schedules/").json()["items"][0]

    assert body["fire_after"] == slot.isoformat().replace("+00:00", "Z")


def test_preview_returns_three_fire_times(client, agent):
    resp = client.post(
        "/api/agents/echo/schedules/preview",
        {"cron": "0 9 * * 5", "timezone": "America/New_York"},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert len(resp.json()["next_runs"]) == 3


def test_preview_rejects_a_bad_cron_without_saving_anything(client, agent):
    resp = client.post(
        "/api/agents/echo/schedules/preview",
        {"cron": "every friday please", "timezone": "UTC"},
        content_type="application/json",
    )
    assert resp.status_code == 422
    assert resp["content-type"] == "application/problem+json"
    assert AgentSchedule.objects.count() == 0
