"""Deterministic review-ingestion — approved clusters -> harness turns."""
from canopy_runner import reviews


class FakeClient:
    def __init__(self, listing, details):
        self._listing = listing        # list of review rows (as /api/reviews/ returns)
        self._details = details         # {review_id: detail dict}
        self.enqueued = []

    def list_reviews(self, status=""):
        assert status == "resolved"
        return self._listing

    def get_review(self, review_id):
        return self._details[review_id]

    def enqueue_turn(self, agent, origin, idem, *, prompt="", origin_ref=None, routing="prefer_local"):
        self.enqueued.append({"agent": agent, "origin": origin, "idem": idem,
                              "prompt": prompt, "origin_ref": origin_ref})
        return {"id": "t-x"}


def _detail(clusters, decisions, gate="product_findings"):
    return {"gate": gate, "request_json": {"clusters": clusters},
            "response_json": {"decisions": decisions}}


def test_enqueues_implemented_cluster_turns():
    clusters = [
        {"id": "eva-first-turn", "dispatch": [
            {"target_agent": "eva", "origin": "email", "prompt": "/turn --thread T",
             "origin_ref": {"thread_id": "T"}}]},
        {"id": "hal-skip-me", "dispatch": [{"target_agent": "hal", "prompt": "/turn"}]},
    ]
    decisions = {"eva-first-turn": {"decision": "implement"},
                 "hal-skip-me": {"decision": "skip"}}
    c = FakeClient([{"id": "r1", "gate": "product_findings"}],
                   {"r1": _detail(clusters, decisions)})
    res = reviews.check_reviews(c)
    assert [e["agent"] for e in c.enqueued] == ["eva"]                 # only implemented
    assert c.enqueued[0]["idem"] == "review-r1-eva-first-turn-0"
    assert c.enqueued[0]["origin_ref"] == {"thread_id": "T"}
    assert res["processed"] == {"r1"}                                  # fully ingested


def test_fanout_cluster_enqueues_one_turn_each():
    clusters = [{"id": "echo-stale-board", "dispatch": [
        {"target_agent": "echo", "prompt": "/turn nudge Sarvesh"},
        {"target_agent": "echo", "prompt": "/turn nudge Amie"}]}]
    c = FakeClient([{"id": "r2", "gate": "product_findings"}],
                   {"r2": _detail(clusters, {"echo-stale-board": {"decision": "implement"}})})
    reviews.check_reviews(c)
    assert [e["idem"] for e in c.enqueued] == \
        ["review-r2-echo-stale-board-0", "review-r2-echo-stale-board-1"]


def test_seen_reviews_are_skipped():
    c = FakeClient([{"id": "r1", "gate": "product_findings"}], {})  # get_review never called
    res = reviews.check_reviews(c, seen=frozenset({"r1"}))
    assert c.enqueued == [] and res["processed"] == set()


def test_non_findings_gate_ignored():
    c = FakeClient([{"id": "r9", "gate": "ddd_narrative"}], {})
    reviews.check_reviews(c)
    assert c.enqueued == []


def test_implemented_without_routing_block_is_logged_and_review_still_handled_once():
    """An approved cluster with no dispatch[] can't be dispatched. The review is still
    marked processed — its decisions are immutable and Ada re-emits as a NEW review, so
    retrying forever would only spam the log every poll."""
    clusters = [{"id": "eva-first-turn"}]  # no dispatch[]
    c = FakeClient([{"id": "r3", "gate": "product_findings"}],
                   {"r3": _detail(clusters, {"eva-first-turn": {"decision": "implement"}})})
    res = reviews.check_reviews(c)
    assert c.enqueued == []            # nothing dispatchable
    assert res["processed"] == {"r3"}  # but handled once — no perpetual re-warning
