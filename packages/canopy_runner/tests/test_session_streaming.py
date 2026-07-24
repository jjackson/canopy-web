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


def test_reattach_resumes_instead_of_skipping_what_you_missed(tmp_path, monkeypatch):
    """The phone-misses-messages bug.

    Detaching dropped the tailer; re-attaching called seek_end() and skipped
    EVERYTHING written while the viewer was away, and reset seq to 0 so the
    replayed ids collided with older ones and got deduped away.
    """
    m._stream_readers.clear()
    m._stream_state.clear()
    p = tmp_path / "echo.jsonl"
    p.write_text(_asst("old history"))
    monkeypatch.setattr(m.transcript, "resolve_transcript", lambda _proj, _task, **_k: p)

    watching = [{"session_id": "s1", "session_key": "echo-1", "project": "echo"}]
    c = _Client(watching)

    m._sync_session_streams(_Cfg(), c)          # attach (skips pre-existing history)
    with open(p, "a") as f:
        f.write(_asst("while watching"))
    m._sync_session_streams(_Cfg(), c)
    assert [e["payload"]["text"] for _s, ev in c.posted for e in ev] == ["while watching"]
    first_seq = c.posted[-1][1][-1]["seq"]

    # viewer closes the chat -> tailer dropped
    c._streams = []
    m._sync_session_streams(_Cfg(), c)
    assert "s1" not in m._stream_readers

    # the agent keeps working while nobody is watching
    with open(p, "a") as f:
        f.write(_asst("missed while away"))

    # viewer re-opens -> the missed message must arrive, with a NON-colliding seq
    c._streams = watching
    m._sync_session_streams(_Cfg(), c)          # re-attach resumes at the saved offset
    m._sync_session_streams(_Cfg(), c)          # ...and reads the appended bytes
    texts = [e["payload"]["text"] for _s, ev in c.posted for e in ev]
    assert "missed while away" in texts, "re-attach skipped what was written while away"
    seqs = [e["seq"] for _s, ev in c.posted for e in ev]
    assert len(seqs) == len(set(seqs)), f"seq restarted and collided: {seqs}"
    assert seqs[-1] > first_seq
