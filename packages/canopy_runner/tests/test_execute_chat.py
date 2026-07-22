"""execute_chat_turn wiring: a chat turn injects into emdash (mocked) and bridges the
assistant reply that appears in the transcript AFTER injection back into the ledger."""
import types

from canopy_runner import execute


def _asst(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def _user(text):
    return {"type": "user", "message": {"content": text}}


class _FakeClient:
    def __init__(self):
        self.events = []
        self.finished = None
        self.failed = None

    def resolve_session(self, *a, **k):
        return {"reuse": False}  # -> create path

    def start(self, *a, **k):
        pass

    def record_session(self, *a, **k):
        pass

    def post_events(self, turn_id, evs):
        self.events.extend(evs)

    def finish(self, turn_id, note=""):
        self.finished = note

    def fail_turn(self, turn_id, note):
        self.failed = note


def test_execute_chat_turn_bridges_the_reply(monkeypatch):
    # emdash transcript GROWS: only the prompt at bridge-start, then the assistant reply.
    states = [
        [_user("hello")],
        [_user("hello"), _asst("Hi there!")],
        [_user("hello"), _asst("Hi there!")],  # stable -> idle completion
    ]
    box = {"i": 0}

    def fake_read(_path):
        i = min(box["i"], len(states) - 1)
        box["i"] += 1
        return states[i]

    monkeypatch.setattr(execute.cdp_control, "create_task", lambda *a, **k: {"task": "echo-1234"})
    monkeypatch.setattr(execute, "_wait_for_transcript", lambda *a, **k: "/tmp/fake.jsonl")
    monkeypatch.setattr(execute.chat_bridge, "read_records", fake_read)
    monkeypatch.setattr(execute.time, "sleep", lambda _s: None)  # instant polls

    cfg = types.SimpleNamespace(cdp_port=9222, emdash_db="/nonexistent")
    client = _FakeClient()
    turn = {
        "id": "t1", "agent_slug": "echo", "project": "", "workspace_slug": "canopy",
        "prompt": "hello", "origin_ref": {"chat_session_id": "s1", "thread_key": "s1"},
    }

    res = execute.execute_chat_turn(cfg, client, "runner1", turn)

    assert res.startswith("chat:t1:")
    assert client.failed is None
    # the assistant reply was bridged as an assistant TurnEvent
    assistant_events = [e for e in client.events if e.get("kind") == "assistant"]
    assert [e["payload"]["text"] for e in assistant_events] == ["Hi there!"]
    assert "bridged" in (client.finished or "")


def test_execute_turn_routes_chat_turns(monkeypatch):
    called = {}

    def _fake_chat(*a, **k):
        called["chat"] = True
        return "chat:x"

    monkeypatch.setattr(execute, "execute_chat_turn", _fake_chat)
    turn = {"id": "t", "origin_ref": {"chat_session_id": "s"}}
    assert execute.execute_turn(None, None, "r", turn) == "chat:x"
    assert called.get("chat") is True
