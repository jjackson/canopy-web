import pytest
from django.contrib.auth import get_user_model

from apps.canopy_sessions.models import Session, RunnerBinding
from apps.harness.models import Runner
from apps.workspaces.models import Workspace

pytestmark = pytest.mark.django_db


def test_binding_is_one_to_one_and_absorbs_tail():
    user = get_user_model().objects.create(username="jj", email="jj@dimagi.com")
    ws = Workspace.objects.create(slug="w1", display_name="W1", created_by=user)
    runner = Runner.objects.create(name="laptop", workspace=ws, location=Runner.LOCAL)
    session = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="feat-x")
    b = RunnerBinding.objects.create(
        session=session, runner=runner, session_key="feat-x",
        tail=[{"role": "assistant", "text": "hi"}], summary="rolling",
    )
    assert session.runner_binding == b
    assert b.tail[0]["text"] == "hi"


def test_emdashsession_is_gone():
    import apps.harness.models as m
    assert not hasattr(m, "EmdashSession")


def test_binding_reusable_by_matches_runner_and_host(db):
    from apps.canopy_sessions.models import RunnerBinding, Session
    from apps.harness.models import Runner
    from apps.workspaces.models import Workspace

    user = get_user_model().objects.create(username="jj2", email="jj@dimagi.com")
    ws = Workspace.objects.create(slug="w2", display_name="W2", created_by=user)
    runner = Runner.objects.create(name="laptop", workspace=ws, host="jj@air", location=Runner.LOCAL)
    session = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="t")
    b = RunnerBinding.objects.create(
        session=session, runner=runner, host="jj@air", session_key="feat-x",
        thread_key="phone:jj:canopy-web", agent_task_ext_id="TASK-9",
    )
    assert b.reusable_by(runner) is True
    # different host on the same runner id -> not reusable (two-account failover invariant)
    runner.host = "jj@studio"
    assert b.reusable_by(runner) is False


def test_binding_partial_unique_on_runner_session_key(db):
    from django.db import IntegrityError, transaction
    from apps.canopy_sessions.models import RunnerBinding, Session
    from apps.harness.models import Runner
    from apps.workspaces.models import Workspace

    user = get_user_model().objects.create(username="jj3", email="jj@dimagi.com")
    ws = Workspace.objects.create(slug="w3", display_name="W3", created_by=user)
    runner = Runner.objects.create(name="laptop", workspace=ws, location=Runner.LOCAL)
    s1 = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="a")
    s2 = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="b")
    RunnerBinding.objects.create(session=s1, runner=runner, session_key="feat-x")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RunnerBinding.objects.create(session=s2, runner=runner, session_key="feat-x")


def test_binding_empty_session_key_not_deduped(db):
    # session_key="" is the transient pre-create state; the partial constraint
    # excludes it so two half-formed bindings on one runner don't collide.
    from apps.canopy_sessions.models import RunnerBinding, Session
    from apps.harness.models import Runner
    from apps.workspaces.models import Workspace

    user = get_user_model().objects.create(username="jj4", email="jj@dimagi.com")
    ws = Workspace.objects.create(slug="w4", display_name="W4", created_by=user)
    runner = Runner.objects.create(name="laptop", workspace=ws, location=Runner.LOCAL)
    s1 = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="a")
    s2 = Session.objects.create(workspace=ws, origin=Session.ORIGIN_RUNNER, title="b")
    RunnerBinding.objects.create(session=s1, runner=runner, session_key="")
    RunnerBinding.objects.create(session=s2, runner=runner, session_key="")  # no IntegrityError
    assert RunnerBinding.objects.filter(session_key="").count() == 2
