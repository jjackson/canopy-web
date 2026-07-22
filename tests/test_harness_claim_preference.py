"""Per-agent runner-KIND preference honored at claim time (Agent.runner_preference).

The preferred kind claims immediately; a lower-preference kind falls back only after
its per-tier head-start elapses (so it still runs the turn if the preferred runner
never shows). A kind absent from a non-empty preference never claims the agent.
This is the fix for "an echo-capable cloud runner races the laptop for echo turns"."""
from __future__ import annotations

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.agents.models import Agent
from apps.harness import services
from apps.harness.models import Runner, Turn
from apps.harness.services import PREFERENCE_TIER_GRACE_SECONDS
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


def _user(name):
    return get_user_model().objects.create_user(username=name, email=f"{name}@dimagi.com")


def _ws(slug, owner):
    ws = Workspace.objects.create(slug=slug, display_name=slug.title(), created_by=owner)
    WorkspaceMembership.objects.create(workspace=ws, user=owner, role=WorkspaceMembership.OWNER)
    return ws


def _runner(pairer, name, kind):
    return Runner.objects.create(
        name=name, kind=kind, host="", paired_by=pairer,
        status=Runner.ONLINE, last_heartbeat_at=timezone.now(),
        capabilities={"agents": ["echo"]},
    )


def _agent(ws, preference):
    return Agent.objects.create(slug="echo", name="Echo", workspace=ws, runner_preference=preference)


def _turn(agent, key, *, age_seconds=0):
    t = Turn.objects.create(agent=agent, origin=Turn.ORIGIN_MANUAL, idempotency_key=key, prompt="hi")
    if age_seconds:
        past = timezone.now() - dt.timedelta(seconds=age_seconds)
        Turn.objects.filter(pk=t.pk).update(created_at=past)
        t.refresh_from_db()
    return t


def _setup(preference):
    jj = _user("jj")
    ws = _ws("connect", jj)
    agent = _agent(ws, preference)
    return jj, ws, agent


# --- baseline: no preference ------------------------------------------------
def test_no_preference_any_eligible_runner_claims():
    jj, ws, agent = _setup([])
    laptop = _runner(jj, "jj-mbp", Runner.EMDASH)
    _turn(agent, "t1")
    assert services.claim_next_turn(laptop) is not None  # unchanged behavior


# --- cloud-first ------------------------------------------------------------
def test_preferred_kind_claims_immediately():
    jj, ws, agent = _setup([Runner.CLOUD, Runner.EMDASH])
    cloud = _runner(jj, "cloud-echo", Runner.CLOUD)
    _turn(agent, "t1")
    claimed = services.claim_next_turn(cloud)
    assert claimed is not None and claimed.claimed_by_id == cloud.id


def test_lower_kind_waits_out_its_head_start_then_falls_back():
    jj, ws, agent = _setup([Runner.CLOUD, Runner.EMDASH])
    laptop = _runner(jj, "jj-mbp", Runner.EMDASH)
    # A FRESH turn: the laptop (rank 1) is still in the cloud's head-start window.
    _turn(agent, "fresh")
    assert services.claim_next_turn(laptop) is None
    # An OLD turn (older than the tier grace): the laptop may now fall back.
    _turn(agent, "old", age_seconds=PREFERENCE_TIER_GRACE_SECONDS + 5)
    claimed = services.claim_next_turn(laptop)
    assert claimed is not None and claimed.idempotency_key == "old"


def test_kind_absent_from_preference_never_claims():
    jj, ws, agent = _setup([Runner.CLOUD])  # laptop kind not listed at all
    laptop = _runner(jj, "jj-mbp", Runner.EMDASH)
    _turn(agent, "old", age_seconds=10_000)  # even very old
    assert services.claim_next_turn(laptop) is None


def test_cloud_first_beats_the_laptop_race():
    # The real scenario: both online, fresh echo turn. Cloud wins; laptop can't take it.
    jj, ws, agent = _setup([Runner.CLOUD, Runner.EMDASH])
    cloud = _runner(jj, "cloud-echo", Runner.CLOUD)
    laptop = _runner(jj, "jj-mbp", Runner.EMDASH)
    _turn(agent, "race")
    assert services.claim_next_turn(laptop) is None       # laptop held back by head-start
    assert services.claim_next_turn(cloud) is not None     # cloud claims it
