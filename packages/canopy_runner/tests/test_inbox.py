"""Deterministic inbox trigger — gmail threads → email-origin turns."""
import json
from types import SimpleNamespace

import pytest

from canopy_runner import inbox


class FakeClient:
    def __init__(self):
        self.enqueued = []

    def enqueue_turn(self, agent, origin, idem, *, prompt="", origin_ref=None, routing="prefer_local"):
        self.enqueued.append({"agent": agent, "origin": origin, "idem": idem,
                              "origin_ref": origin_ref, "prompt": prompt})
        return {"id": "t-x"}


def _runner(threads):
    payload = json.dumps({"threads": threads})

    def run(cmd, capture_output, text, timeout):
        return SimpleNamespace(returncode=0, stdout=payload, stderr="")
    return run


def test_enqueues_one_turn_per_thread():
    client = FakeClient()
    r = _runner([
        {"id": "thr-1", "from": "Hal <hal@dimagi-ai.com>", "subject": "re: bednet", "messageCount": 3},
        {"id": "thr-2", "from": "x@y.com", "subject": "hi", "messageCount": 1},
    ])
    ids = inbox.check_inbox(client, "hal", mailbox="hal@dimagi-ai.com", gog_client="canopy", runner=r)
    assert ids == ["thr-1", "thr-2"]
    assert client.enqueued[0]["origin"] == "email"
    assert client.enqueued[0]["origin_ref"]["thread_id"] == "thr-1"
    assert client.enqueued[0]["prompt"] == "/turn --thread thr-1"


def test_idempotency_key_includes_message_count():
    client = FakeClient()
    r = _runner([{"id": "thr-1", "from": "Hal", "subject": "s", "messageCount": 3}])
    inbox.check_inbox(client, "hal", mailbox="m", gog_client="c", runner=r)
    assert client.enqueued[0]["idem"] == "email-hal-thr-1-3"  # a new reply (count 4) -> new key


def test_empty_inbox_enqueues_nothing():
    client = FakeClient()
    assert inbox.check_inbox(client, "hal", mailbox="m", gog_client="c", runner=_runner([])) == []
    assert client.enqueued == []


def test_gog_failure_raises_inboxerror():
    def fail(cmd, capture_output, text, timeout):
        return SimpleNamespace(returncode=1, stdout="", stderr="auth expired")
    with pytest.raises(inbox.InboxError, match="auth expired"):
        inbox.check_inbox(FakeClient(), "hal", mailbox="m", gog_client="c", runner=fail)
