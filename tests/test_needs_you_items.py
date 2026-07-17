"""Items in the supervisor inbox — Phase 2, additively.

needs_you keeps its existing projections (tasks, run gates, the schedule nag)
until their producers migrate in Phases 3-4. This adds Items ALONGSIDE them: a
switch to items-only here would empty the inbox, because nothing else has moved
yet.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.agents.models import Agent
from apps.agents import services
from apps.harness.models import Item, Turn
from apps.workspaces import services as wsvc

pytestmark = pytest.mark.django_db


@pytest.fixture
def ada(db):
    # ensure_default_workspace() returns None when no user exists (it needs an
    # owner), which would leave the agent unhomed and its deep-links untenanted.
    # Production always has a user, so mirror that.
    get_user_model().objects.create_user(username="jj@dimagi.com", email="jj@dimagi.com")
    ws = wsvc.ensure_default_workspace()
    return Agent.objects.create(slug="ada", name="Ada", workspace=ws)


def _item(ada, **kw):
    kw.setdefault("idempotency_key", f"k-{kw.get('title', 'x')}")
    kw.setdefault("kind", Item.REVIEW)
    kw.setdefault("title", "x")
    kw.setdefault("origin", Turn.ORIGIN_API)
    return Item.objects.create(agent=ada, **kw)


def test_an_open_review_item_lands_in_the_review_band(ada):
    _item(ada, title="hal: discard 81 junk emails", body="All 81 are automated.")

    out = services.needs_you(ada)

    review = [i for i in out["items"] if i["type"] == "review"]
    assert [i["title"] for i in review] == ["hal: discard 81 junk emails"]
    assert review[0]["ref_kind"] == "item"
    assert out["waiting_count"] == 1


def test_an_open_question_item_lands_in_the_question_band(ada):
    _item(ada, kind=Item.QUESTION, title="which repo?")

    out = services.needs_you(ada)

    question = [i for i in out["items"] if i["type"] == "question"]
    assert [i["title"] for i in question] == ["which repo?"]


def test_a_decided_item_is_gone_from_the_inbox(ada):
    item = _item(ada, title="done with this")
    services_h = __import__("apps.harness.services", fromlist=["x"])
    services_h.decide_item(item, decision=Item.SKIP, comment="", by="jj@dimagi.com", actor_workspace_slugs={wsvc.DEFAULT_WORKSPACE_SLUG})

    out = services.needs_you(ada)

    assert out["waiting_count"] == 0
    assert [i for i in out["items"] if i["ref_kind"] == "item"] == []


def test_a_dismissed_item_is_gone_from_the_inbox(ada):
    item = _item(ada, title="raised in error")
    services_h = __import__("apps.harness.services", fromlist=["x"])
    services_h.dismiss_item(item, by="jj@dimagi.com")

    assert services.needs_you(ada)["waiting_count"] == 0


def test_items_carry_a_deep_link_to_their_batch(ada):
    _item(ada, title="in a batch", batch_key="fleet-audit-2026-07-14")

    out = services.needs_you(ada)
    row = next(i for i in out["items"] if i["ref_kind"] == "item")

    assert row["url"] == "/w/dimagi/agents/ada/items?batch=fleet-audit-2026-07-14"


def test_items_do_not_displace_the_existing_projections(ada):
    """The whole point of Phase 2 being additive: a suggested task still shows."""
    from apps.agents.models import AgentTask

    AgentTask.objects.create(
        agent=ada, ext_id="t1", title="a suggested task", status=AgentTask.SUGGESTED,
    )
    _item(ada, title="an item")

    out = services.needs_you(ada)

    titles = {i["title"] for i in out["items"]}
    assert titles == {"a suggested task", "an item"}
    assert out["waiting_count"] == 2
