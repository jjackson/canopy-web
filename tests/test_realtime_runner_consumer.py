"""RC1 — RunnerConsumer: PAT-authed control channel, wake-on-enqueue, claim over WS.

The runner keeps a persistent socket; enqueue publishes a wake to its workspace's
runnable group (the runner claims on it), and claim/heartbeat frames call the same
harness services the REST routes do. Postgres stays the source of truth."""
from __future__ import annotations

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser, User
from django.utils import timezone

from apps.agents.models import Agent
from apps.harness import services
from apps.harness.models import Runner, Turn
from apps.realtime.consumers import RunnerConsumer
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db(transaction=True)


def _setup():
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="connect", display_name="Connect", created_by=user)
    WorkspaceMembership.objects.create(user=user, workspace=ws, role=WorkspaceMembership.OWNER)
    agent = Agent.objects.create(slug="echo", name="Echo", workspace=ws, owner=user)
    runner = Runner.objects.create(
        name="jj-mbp", kind=Runner.EMDASH, paired_by=user,
        status=Runner.ONLINE, last_heartbeat_at=timezone.now(),
        capabilities={"agents": ["echo"]},
    )
    return user, ws, agent, runner


async def _connect(runner_id, user):
    comm = WebsocketCommunicator(RunnerConsumer.as_asgi(), f"/ws/runner/{runner_id}/")
    comm.scope["user"] = user
    comm.scope["url_route"] = {"kwargs": {"runner_id": str(runner_id)}}
    return comm


# --- auth / ownership --------------------------------------------------------
async def test_anonymous_rejected():
    user, _ws, _a, runner = await database_sync_to_async(_setup)()
    comm = await _connect(runner.id, AnonymousUser())
    connected, code = await comm.connect()
    assert connected is False and code == 4001


async def test_non_owner_rejected():
    user, _ws, _a, runner = await database_sync_to_async(_setup)()
    other = await database_sync_to_async(User.objects.create_user)("x", "x@dimagi.com", "pw")
    comm = await _connect(runner.id, other)
    connected, code = await comm.connect()
    assert connected is False and code == 4003


async def test_owner_connects():
    user, _ws, _a, runner = await database_sync_to_async(_setup)()
    comm = await _connect(runner.id, user)
    connected, _ = await comm.connect()
    assert connected is True
    await comm.disconnect()


# --- wake on enqueue ---------------------------------------------------------
async def test_enqueue_wakes_the_runner():
    user, ws, agent, runner = await database_sync_to_async(_setup)()
    comm = await _connect(runner.id, user)
    await comm.connect()

    @database_sync_to_async
    def _enqueue():
        services.enqueue_turn(agent=agent, origin=Turn.ORIGIN_MANUAL,
                              idempotency_key="w1", prompt="hi")

    await _enqueue()
    frame = await comm.receive_json_from(timeout=2)
    assert frame == {"type": "wake"}
    await comm.disconnect()


# --- claim over the socket ---------------------------------------------------
async def test_claim_over_ws_returns_a_turn():
    user, ws, agent, runner = await database_sync_to_async(_setup)()

    @database_sync_to_async
    def _enqueue():
        services.enqueue_turn(agent=agent, origin=Turn.ORIGIN_MANUAL,
                              idempotency_key="c1", prompt="do the thing")

    await _enqueue()  # queued before connect — so no wake reaches this socket
    comm = await _connect(runner.id, user)
    await comm.connect()

    await comm.send_json_to({"action": "claim"})
    frame = await comm.receive_json_from(timeout=2)
    assert frame["type"] == "claim.result"
    assert frame["turn"]["target"] == "echo"
    assert frame["turn"]["prompt"] == "do the thing"
    await comm.disconnect()


async def test_claim_over_ws_empty_when_nothing_queued():
    user, _ws, _a, runner = await database_sync_to_async(_setup)()
    comm = await _connect(runner.id, user)
    await comm.connect()
    await comm.send_json_to({"action": "claim"})
    frame = await comm.receive_json_from(timeout=2)
    assert frame == {"type": "claim.result", "turn": None}
    await comm.disconnect()
