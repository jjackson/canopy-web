"""Runner backfill: read a session's full transcript and ship it as {role,text}
messages when the server asks. Fake client + tmp transcript."""
import json

from canopy_runner import main as m


class _Cfg:
    runner_id = "r"


class _Client:
    def __init__(self, backfills):
        self._backfills = backfills
        self.shipped = []  # (session_id, messages)

    def sync_backfills(self, runner_id):
        return self._backfills

    def post_session_backfill(self, runner_id, session_id, messages):
        self.shipped.append((session_id, messages))


def _asst(t):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": t}]}}) + "\n"


def _user(t):
    return json.dumps({"type": "user", "message": {"content": t}}) + "\n"


def test_drains_backfill_and_ships_full_transcript(tmp_path, monkeypatch):
    p = tmp_path / "echo.jsonl"
    p.write_text(_user("q1") + _asst("a1") + _user("q2") + _asst("a2"))
    monkeypatch.setattr(m.transcript, "resolve_transcript", lambda _proj, _task, **_k: p)

    c = _Client([{"session_id": "s1", "session_key": "echo-1", "project": "echo"}])
    m._drain_backfills(_Cfg(), c)

    assert len(c.shipped) == 1
    sid, messages = c.shipped[0]
    assert sid == "s1"
    assert [(x["role"], x["text"]) for x in messages] == [
        ("user", "q1"), ("assistant", "a1"), ("user", "q2"), ("assistant", "a2"),
    ]


def test_drain_skips_when_transcript_missing(monkeypatch):
    monkeypatch.setattr(m.transcript, "resolve_transcript", lambda *a, **k: None)
    c = _Client([{"session_id": "s1", "session_key": "echo-1", "project": "echo"}])
    m._drain_backfills(_Cfg(), c)
    assert c.shipped == []  # nothing to ship; runner-offline path stays server-side
