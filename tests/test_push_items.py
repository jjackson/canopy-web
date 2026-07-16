"""push must follow the badge. needs_you now counts Items, so a new Item has to
mark its agent dirty — otherwise the phone and the badge silently disagree, which
is worse than no push at all."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.agents.models import Agent
from apps.harness.models import Item, Turn
from apps.workspaces import services as wsvc

pytestmark = pytest.mark.django_db


@pytest.fixture
def ada(db):
    get_user_model().objects.create_user(username="jj@dimagi.com", email="jj@dimagi.com")
    ws = wsvc.ensure_default_workspace()
    return Agent.objects.create(slug="ada", name="Ada", workspace=ws)


def test_raising_an_item_marks_its_agent_dirty(ada):
    with patch("apps.push.signals.mark_dirty") as mark_dirty:
        Item.objects.create(
            agent=ada, kind=Item.REVIEW, title="hal: discard 81 junk emails",
            origin=Turn.ORIGIN_API, idempotency_key="k1",
        )

    mark_dirty.assert_called_once_with(ada.id)


def test_deciding_an_item_marks_its_agent_dirty(ada):
    """A decided item leaves the waiting set. The count only drops, and push never
    sends on a drop — but the snapshot must still be updated, or the NEXT rise
    computes against a stale baseline and never fires."""
    item = Item.objects.create(
        agent=ada, kind=Item.REVIEW, title="x", origin=Turn.ORIGIN_API,
        idempotency_key="k2",
    )

    with patch("apps.push.signals.mark_dirty") as mark_dirty:
        item.state = Item.DECIDED
        item.save(update_fields=["state"])

    mark_dirty.assert_called_once_with(ada.id)
