"""A queued turn nothing can claim must be LOUD, not silent.

Observed: a `project=ace` turn sat QUEUED for 12 hours because every online
runner declared `projects: ['canopy-web']`. `enqueue_turn` accepted it happily
and nothing ever said the turn was unrunnable.

The detector shares `runner_target_q` with `claim_next_turn`, so "can anyone run
this?" cannot disagree with what claiming actually does.
"""
import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.agents.models import Agent
from apps.harness import services
from apps.harness.models import Runner, Turn
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


def _ctx(*, agents=(), projects=(), sessions=False, online=True):
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="w1", display_name="W1", created_by=user)
    WorkspaceMembership.objects.create(user=user, workspace=ws, role=WorkspaceMembership.OWNER)
    Runner.objects.create(
        name="jj-mbp", workspace=ws, location=Runner.LOCAL, paired_by=user, host="jj@mbp",
        status=Runner.ONLINE if online else Runner.DISCONNECTED,
        last_heartbeat_at=timezone.now() if online else None,
        capabilities={"agents": list(agents), "projects": list(projects), "sessions": sessions},
    )
    return user, ws


def _project_turn(ws, project, key="k1"):
    return services.enqueue_turn(
        project=project, workspace=ws, origin=Turn.ORIGIN_API,
        idempotency_key=key, prompt="Go",
    )[0]


def test_flags_a_project_turn_no_runner_declares():
    """The exact 12-hour stall."""
    user, ws = _ctx(agents=["ace"], projects=["canopy-web"])
    _project_turn(ws, "ace")
    rows = services.unclaimable_queued_turns(user)
    assert len(rows) == 1
    assert rows[0]["target"] == "project ace"
    assert "declares the repo 'ace'" in rows[0]["reason"]
    assert rows[0]["prompt"] == "Go"


def test_silent_when_the_runner_declares_the_repo():
    user, ws = _ctx(agents=["ace"], projects=["canopy-web", "ace"])
    _project_turn(ws, "ace")
    assert services.unclaimable_queued_turns(user) == []


def test_flags_an_agent_turn_no_runner_declares():
    user, ws = _ctx(agents=["ace"], projects=["canopy-web"])
    other = Agent.objects.create(slug="ghost", name="Ghost", workspace=ws)
    services.enqueue_turn(agent=other, origin=Turn.ORIGIN_API, idempotency_key="k2", prompt="hi")
    rows = services.unclaimable_queued_turns(user)
    assert [r["target"] for r in rows] == ["agent ghost"]


def test_an_offline_runner_does_not_count_as_coverage():
    """A declared-but-dead runner must not mask the stall."""
    user, ws = _ctx(agents=["ace"], projects=["ace"], online=False)
    _project_turn(ws, "ace")
    rows = services.unclaimable_queued_turns(user)
    assert [r["target"] for r in rows] == ["project ace"]


def test_a_degraded_runner_does_count():
    """DEGRADED = CDP down, still polling and still able to claim once CDP returns."""
    user, ws = _ctx(agents=["ace"], projects=["ace"])
    Runner.objects.update(status=Runner.DEGRADED)
    _project_turn(ws, "ace")
    assert services.unclaimable_queued_turns(user) == []


def test_session_turns_need_a_session_capable_runner():
    from apps.canopy_sessions.models import Session
    user, ws = _ctx(agents=["ace"], projects=["canopy-web"], sessions=False)
    s = Session.objects.create(workspace=ws, created_by=user, title="chat")
    services.enqueue_turn(session=s, origin=Turn.ORIGIN_API, idempotency_key="k3", prompt="hi")
    assert [r["target"] for r in services.unclaimable_queued_turns(user)] == ["session"]

    Runner.objects.update(capabilities={"agents": [], "projects": [], "sessions": True})
    assert services.unclaimable_queued_turns(user) == []


def test_endpoint_returns_the_rows(client):
    user, ws = _ctx(agents=["ace"], projects=["canopy-web"])
    _project_turn(ws, "ace")
    client.force_login(user)
    body = client.get("/api/harness/turns/unclaimable").json()
    assert [r["target"] for r in body] == ["project ace"]
