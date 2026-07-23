import pytest
from django.contrib.auth import get_user_model

from apps.canopy_sessions import services
from apps.canopy_sessions.models import Message, Session
from apps.workspaces.models import Workspace

pytestmark = pytest.mark.django_db


def _session_with(n: int) -> Session:
    # Workspace.created_by is a required FK (NOT NULL); the brief's helper is
    # otherwise verbatim.
    owner = get_user_model().objects.create_user("owner", "owner@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="w1", display_name="W1", created_by=owner)
    s = Session.objects.create(workspace=ws, title="t")
    for i in range(n):
        Message.objects.create(
            session=s, turn_index=i, role=Message.USER, plaintext=f"m{i}",
        )
    return s


def test_tail_default_is_20():
    assert services.SESSION_TAIL_DEFAULT == 20


def test_tail_returns_last_n_chronological_with_cursor():
    s = _session_with(50)
    msgs, has_more, oldest = services.tail_messages(s)
    assert [m.turn_index for m in msgs] == list(range(30, 50))  # last 20, ascending
    assert has_more is True
    assert oldest == 30


def test_tail_short_session_has_no_more():
    s = _session_with(3)
    msgs, has_more, oldest = services.tail_messages(s)
    assert [m.turn_index for m in msgs] == [0, 1, 2]
    assert has_more is False
    assert oldest == 0


def test_tail_empty_session():
    s = _session_with(0)
    msgs, has_more, oldest = services.tail_messages(s)
    assert msgs == []
    assert has_more is False
    assert oldest is None


def test_messages_before_pages_backward():
    s = _session_with(50)
    # scroll-back from the tail's oldest (30), page size 10
    page, has_more = services.messages_before(s, before=30, limit=10)
    assert [m.turn_index for m in page] == list(range(20, 30))  # chronological window
    assert has_more is True
    # walk to the beginning
    page, has_more = services.messages_before(s, before=10, limit=10)
    assert [m.turn_index for m in page] == list(range(0, 10))
    assert has_more is False  # nothing older than index 0


def test_all_messages_returns_everything():
    s = _session_with(50)
    msgs, has_more, oldest = services.all_messages(s)
    assert len(msgs) == 50
    assert has_more is False
    assert oldest == 0
