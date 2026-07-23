"""Runner live-streaming: tail a desired session's transcript and post new assistant
text as live events; stop when it's no longer desired. Fake client + tmp transcript."""
import json

from canopy_runner import main as m


class _Cfg:
    runner_id = "r"


class _Client:
    def __init__(self, streams):
        self._streams = streams
        self.posted = []          # (session_id, events)

    def sync_streams(self, runner_id):
        return self._streams

    def post_session_stream(self, runner_id, session_id, events):
        self.posted.append((session_id, events))


def _asst(text):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}) + "\n"


def test_streams_new_assistant_text_then_stops(tmp_path, monkeypatch):
    m._stream_readers.clear()
    p = tmp_path / "echo.jsonl"
    p.write_text(_asst("old history"))  # pre-existing; seek_end skips it
    monkeypatch.setattr(m.transcript, "resolve_transcript", lambda _proj, _task, **_k: p)

    streams = [{"session_id": "s1", "session_key": "echo-1", "project": "echo"}]
    c = _Client(streams)

    # first tick: registers the tailer at end-of-file -> no events yet
    m._sync_session_streams(_Cfg(), c)
    assert c.posted == []

    # the session speaks -> next tick posts the new assistant text as a live event
    with open(p, "a") as f:
        f.write(_asst("live reply"))
    m._sync_session_streams(_Cfg(), c)
    assert len(c.posted) == 1
    sid, events = c.posted[0]
    assert sid == "s1"
    assert [e["payload"]["text"] for e in events] == ["live reply"]
    assert events[0]["kind"] == "assistant"
    assert events[0]["seq"] == 0

    # a further reply increments seq monotonically
    with open(p, "a") as f:
        f.write(_asst("more"))
    m._sync_session_streams(_Cfg(), c)
    assert c.posted[-1][1][0]["seq"] == 1

    # no longer desired -> the tailer is dropped, nothing posts
    c._streams = []
    m._sync_session_streams(_Cfg(), c)
    assert "s1" not in m._stream_readers


def test_sync_streams_survives_client_error(monkeypatch):
    m._stream_readers.clear()

    class _Boom:
        def sync_streams(self, rid):
            raise RuntimeError("network")

    m._sync_session_streams(_Cfg(), _Boom())  # must not raise
    assert m._stream_readers == {}
