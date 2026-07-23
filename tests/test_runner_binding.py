import pytest
from django.contrib.auth import get_user_model

from apps.chat.models import Session, RunnerBinding
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
