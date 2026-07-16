"""Item schemas — the wire contract producers and the inbox share."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.harness.schemas import ItemDecideIn, ItemIn, TurnSpecIn


def test_turnspec_target_agent_defaults_to_self():
    spec = TurnSpecIn(prompt="/ada:conduct")
    assert spec.target_agent == ""


def test_item_requires_a_title_and_key():
    with pytest.raises(ValidationError):
        ItemIn(kind="review", origin="api")


def test_item_rejects_an_origin_outside_the_choices():
    # `origin` maps to a max_length=10 column with a fixed choice set; an out-of-set
    # value must 422 at the boundary, not reach the DB and 500 (Postgres-only, so
    # SQLite CI can't catch it).
    with pytest.raises(ValidationError):
        ItemIn(title="t", idempotency_key="k", origin="audit")


def test_turnspec_rejects_bad_origin_and_routing():
    with pytest.raises(ValidationError):
        TurnSpecIn(prompt="/ada:conduct", origin="not-an-origin")
    with pytest.raises(ValidationError):
        TurnSpecIn(prompt="/ada:conduct", routing="teleport")


def test_item_rejects_a_notify_kind():
    """notify is not an item — it is the timeline."""
    with pytest.raises(ValidationError):
        ItemIn(kind="notify", title="a sync posted", origin="api", idempotency_key="k")


def test_decide_rejects_a_verb_outside_the_closed_set():
    with pytest.raises(ValidationError):
        ItemDecideIn(decision="yolo")


def test_decide_allows_a_blank_decision_for_a_question_answer():
    assert ItemDecideIn(decision="", comment="canopy-web").comment == "canopy-web"
