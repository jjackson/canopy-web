"""CDP executor — resolve → reuse-or-create, runner owns the routing lifecycle."""
from types import SimpleNamespace

import pytest

from canopy_runner import cdp_control, execute


def _cfg():
    return SimpleNamespace(cdp_port=9222, runner_id="r-1")


class FakeClient:
    def __init__(self, plan):
        self.plan = plan
        self.calls = []          # method log
        self.events = []
        self.started = []
        self.finished = []
        self.failed = []
        self.recorded = []

    def resolve_session(self, runner_id, agent, thread_key):
        self.calls.append(("resolve", agent, thread_key))
        return dict(self.plan)

    def start(self, turn_id, session_id=""):
        self.started.append(turn_id)

    def finish(self, turn_id, note=""):
        self.finished.append((turn_id, note))

    def fail_turn(self, turn_id, note):
        self.failed.append((turn_id, note))

    def post_events(self, turn_id, events):
        self.events.append((turn_id, events))

    def record_session(self, runner_id, agent, thread_key, **kw):
        self.recorded.append((agent, thread_key, kw))


def _turn(**kw):
    d = {"id": "t-1", "agent_slug": "hal", "origin_ref": {}, "prompt": "do the thing"}
    d.update(kw)
    return d


def test_reuse_sends_into_existing_session(monkeypatch):
    sent = {}
    monkeypatch.setattr(cdp_control, "open_and_send",
                        lambda task, text, port=9222: sent.update(task=task, text=text) or {"ok": True})
    monkeypatch.setattr(cdp_control, "create_task",
                        lambda *a, **k: pytest.fail("must NOT create when reusing"))
    client = FakeClient({"reuse": True, "emdash_task_id": "shaky-baths-listen", "summary": ""})
    turn = _turn(origin_ref={"thread_id": "thr-1"})
    result = execute.execute_turn(_cfg(), client, "r-1", turn)
    assert result == "reused:t-1"
    assert sent == {"task": "shaky-baths-listen", "text": "do the thing"}
    assert client.started == ["t-1"] and client.finished and "existing session" in client.finished[0][1]


def test_reuse_falls_back_to_create_only_when_task_not_found(monkeypatch):
    def gone(task, text, port=9222):
        raise cdp_control.CDPError('TASK_NOT_FOUND: no task "archived-one"')
    created = {}
    monkeypatch.setattr(cdp_control, "open_and_send", gone)
    monkeypatch.setattr(cdp_control, "create_task",
                        lambda project, prompt, task_name="", port=9222: created.update(project=project, prompt=prompt) or {"task": "new-task-x"})
    client = FakeClient({"reuse": True, "emdash_task_id": "archived-one", "summary": "prior ctx"})
    result = execute.execute_turn(_cfg(), client, "r-1", _turn(origin_ref={"thread_id": "thr-1"}))
    assert result.startswith("created:t-1:new-task-x")
    assert created["project"] == "hal"
    assert "prior ctx" in created["prompt"]      # rehydrated on fallback


def test_transient_reuse_send_failure_never_duplicates(monkeypatch):
    """The bug that spawned two Hal sessions: a send glitch on an EXISTING task must
    fail the turn, NOT create a duplicate + re-point the link."""
    def glitch(task, text, port=9222):
        raise cdp_control.CDPError("locator.click: Timeout 30000ms exceeded")  # not TASK_NOT_FOUND
    monkeypatch.setattr(cdp_control, "open_and_send", glitch)
    monkeypatch.setattr(cdp_control, "create_task",
                        lambda *a, **k: pytest.fail("must NOT create a duplicate on a transient send failure"))
    client = FakeClient({"reuse": True, "emdash_task_id": "live-session", "summary": "ctx"})
    result = execute.execute_turn(_cfg(), client, "r-1", _turn(origin_ref={"thread_id": "thr-1"}))
    assert result == "failed:t-1"
    assert client.failed and "not spawning a duplicate" in client.failed[0][1]
    assert client.recorded == []   # link NOT re-pointed — the original session stays canonical


def test_create_new_thread_rehydrates_from_summary(monkeypatch):
    created = {}
    monkeypatch.setattr(cdp_control, "create_task",
                        lambda project, prompt, task_name="", port=9222: created.update(prompt=prompt) or {"task": "fresh"})
    # other-account plan: reuse False but summary present
    client = FakeClient({"reuse": False, "new_thread": False, "emdash_task_id": "etask-A",
                         "summary": "what account A did"})
    result = execute.execute_turn(_cfg(), client, "r-1", _turn(origin_ref={"thread_id": "thr-1"}))
    assert result.startswith("created:t-1:fresh")
    assert "what account A did" in created["prompt"]
    assert client.recorded and client.recorded[0][0] == "hal"


def test_create_failure_fails_the_turn(monkeypatch):
    def boom(project, prompt, task_name="", port=9222):
        raise cdp_control.CDPError("emdash not on debug port")
    monkeypatch.setattr(cdp_control, "create_task", boom)
    client = FakeClient({"reuse": False, "new_thread": True, "summary": ""})
    result = execute.execute_turn(_cfg(), client, "r-1", _turn())
    assert result == "failed:t-1"
    assert client.failed and "emdash create failed" in client.failed[0][1]


def test_thread_key_defaults_to_agent_main_when_no_ref(monkeypatch):
    monkeypatch.setattr(cdp_control, "create_task", lambda *a, **k: {"task": "x"})
    client = FakeClient({"reuse": False, "new_thread": True, "summary": ""})
    execute.execute_turn(_cfg(), client, "r-1", _turn(origin_ref={}))
    assert client.calls[0] == ("resolve", "hal", "hal:main")
