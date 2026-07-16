"""dispatch() — an approved Item becomes work. Self by default; anyone on request."""
from __future__ import annotations

import pytest

from apps.agents.models import Agent
from apps.harness.dispatch import TurnSpec, dispatch
from apps.harness.models import Item, Turn
from apps.workspaces import services as wsvc

pytestmark = pytest.mark.django_db


@pytest.fixture
def ws():
    return wsvc.ensure_default_workspace()


@pytest.fixture
def ada(ws):
    return Agent.objects.create(slug="ada", name="Ada", workspace=ws)


@pytest.fixture
def hal(ws):
    return Agent.objects.create(slug="hal", name="Hal", workspace=ws)


def _item(agent, **kw):
    kw.setdefault("idempotency_key", f"k-{agent.slug}-{kw.get('title', 'x')}")
    kw.setdefault("kind", Item.REVIEW)
    kw.setdefault("title", "x")
    kw.setdefault("origin", Turn.ORIGIN_API)
    return Item.objects.create(agent=agent, **kw)


def test_empty_target_agent_dispatches_to_the_items_own_agent(ada):
    item = _item(ada, dispatch=[{"prompt": "/ada:conduct"}])

    turns = dispatch(item)

    assert [t.agent for t in turns] == [ada]
    assert turns[0].prompt == "/ada:conduct"
    assert turns[0].raised_from == item


def test_named_target_agent_dispatches_to_that_agent(ada, hal):
    item = _item(ada, dispatch=[{"target_agent": "hal", "prompt": "/hal:turn", "origin": "email"}])

    turns = dispatch(item)

    assert [t.agent for t in turns] == [hal]
    assert turns[0].origin == "email"


def test_dispatch_is_idempotent_per_entry(ada):
    item = _item(ada, dispatch=[{"prompt": "/ada:conduct"}])

    first = dispatch(item)
    second = dispatch(item)

    assert [t.id for t in first] == [t.id for t in second]
    assert Turn.objects.count() == 1


def test_an_item_with_no_dispatch_enqueues_nothing(ada):
    item = _item(ada, dispatch=[])

    assert dispatch(item) == []
    assert Turn.objects.count() == 0


def test_an_unknown_target_agent_raises_rather_than_silently_dropping(ada):
    item = _item(ada, dispatch=[{"target_agent": "ghost", "prompt": "/ghost:turn"}])

    with pytest.raises(ValueError, match="ghost"):
        dispatch(item)


def test_each_entry_gets_its_own_turn(ada, hal):
    item = _item(ada, dispatch=[
        {"target_agent": "hal", "prompt": "/hal:turn"},
        {"prompt": "/ada:conduct"},
    ])

    turns = dispatch(item)

    assert [t.agent for t in turns] == [hal, ada]


def test_a_spec_with_no_prompt_falls_back_to_the_targets_turn(ada, hal):
    item = _item(ada, dispatch=[{"target_agent": "hal"}])

    turns = dispatch(item)

    assert turns[0].prompt == "/hal:turn"


def test_turnspec_defaults_target_self():
    assert TurnSpec(prompt="/x").target_agent == ""
