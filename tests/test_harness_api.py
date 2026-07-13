"""API-level tests for /api/harness (runner pairing, claim loop, turn lifecycle)."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.agents.models import Agent
from apps.harness.models import Runner, Turn

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


def _pair(client) -> str:
    resp = client.post(
        "/api/harness/runners/",
        {"name": "jj-mbp", "kind": "emdash", "capabilities": {"agents": ["echo"]}},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()["id"]


def _hb(client, rid, active=None, degraded=False):
    return client.post(
        f"/api/harness/runners/{rid}/heartbeat",
        {"active_turn_ids": active or [], "degraded": degraded, "note": ""},
        content_type="application/json",
    )


def test_pair_heartbeat_claim_cycle(client, agent):
    rid = _pair(client)
    assert _hb(client, rid).status_code == 200

    enq = client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    )
    assert enq.status_code == 201

    claim = client.post(f"/api/harness/runners/{rid}/claim")
    assert claim.status_code == 200
    turn = claim.json()
    assert turn["status"] == "claimed" and turn["agent_slug"] == "echo"

    again = client.post(f"/api/harness/runners/{rid}/claim")
    assert again.status_code == 204


def test_enqueue_replays_on_same_key(client, agent):
    body = {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"}
    first = client.post("/api/harness/turns/", body, content_type="application/json")
    second = client.post("/api/harness/turns/", body, content_type="application/json")
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_enqueue_stacks_behind_busy_lane(client, agent):
    client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    )
    resp = client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "slack", "idempotency_key": "k2"},
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "queued"


def test_event_append_and_cursor_read(client, agent):
    enq = client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    ).json()
    tid = enq["id"]
    resp = client.post(
        f"/api/harness/turns/{tid}/events",
        {"events": [{"kind": "status", "payload": {"s": "x"}}, {"kind": "assistant", "payload": {"text": "hi"}}]},
        content_type="application/json",
    )
    assert resp.status_code == 200 and resp.json()["count"] == 2
    # enqueue itself writes no event (services.enqueue_turn is silent);
    # our two posted events get seq 1 and 2.
    events = client.get(f"/api/harness/turns/{tid}/events?after=0").json()["events"]
    assert [e["seq"] for e in events] == [1, 2]


def test_start_and_finish(client, agent):
    rid = _pair(client)
    assert _hb(client, rid).status_code == 200
    tid = client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    ).json()["id"]
    claimed = client.post(f"/api/harness/runners/{rid}/claim")
    assert claimed.status_code == 200 and claimed.json()["id"] == tid
    started = client.post(
        f"/api/harness/turns/{tid}/start", {"session_id": "abc"}, content_type="application/json"
    )
    assert started.status_code == 200 and started.json()["status"] == "running"
    finished = client.post(
        f"/api/harness/turns/{tid}/finish",
        {"status": "done", "result_note": "2 applied"},
        content_type="application/json",
    )
    assert finished.status_code == 200 and finished.json()["status"] == "done"


def test_finish_on_queued_turn_is_409(client, agent):
    tid = client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    ).json()["id"]
    resp = client.post(
        f"/api/harness/turns/{tid}/finish",
        {"status": "done", "result_note": "n/a"},
        content_type="application/json",
    )
    assert resp.status_code == 409, resp.content


def test_list_filter_by_agent_and_status(client, agent):
    # the exact query the drain-turn skill issues
    client.post(
        "/api/harness/turns/",
        {"agent_slug": "echo", "origin": "manual", "idempotency_key": "k1"},
        content_type="application/json",
    )
    resp = client.get("/api/harness/turns/?agent=echo&status=claimed,running,queued")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1 and body[0]["agent_slug"] == "echo"
    empty = client.get("/api/harness/turns/?agent=echo&status=done")
    assert empty.status_code == 200 and empty.json() == []


def test_anonymous_is_401(agent):
    c = Client()
    resp = c.get("/api/harness/turns/")
    assert resp.status_code == 401
