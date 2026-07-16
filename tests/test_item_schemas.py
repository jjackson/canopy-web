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
        ItemIn(kind="review", origin="audit")


def test_item_rejects_a_notify_kind():
    """notify is not an item — it is the timeline."""
    with pytest.raises(ValidationError):
        ItemIn(kind="notify", title="a sync posted", origin="api", idempotency_key="k")


def test_decide_rejects_a_verb_outside_the_closed_set():
    with pytest.raises(ValidationError):
        ItemDecideIn(decision="yolo")


def test_decide_allows_a_blank_decision_for_a_question_answer():
    assert ItemDecideIn(decision="", comment="canopy-web").comment == "canopy-web"
