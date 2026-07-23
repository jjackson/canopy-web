"""The emdash-response bridge: tail assistant text + idle-based completion."""
from canopy_runner.chat_bridge import bridge_response, new_assistant_texts, transcript_messages


def _asst(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def _user(text):
    return {"type": "user", "message": {"content": text}}


def _tool():
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}}


def test_new_assistant_texts_after_offset():
    recs = [_user("hi"), _asst("hello"), _tool(), _asst("done")]
    assert new_assistant_texts(recs, 0) == ["hello", "done"]
    assert new_assistant_texts(recs, 2) == ["done"]  # only after the offset
    assert new_assistant_texts([_tool()], 0) == []   # tool-only -> no text


def test_bridge_posts_new_assistant_texts_and_completes_on_idle():
    states = [
        [_user("prompt")],                                    # only the injected prompt
        [_user("prompt"), _asst("thinking")],                 # first assistant chunk
        [_user("prompt"), _asst("thinking"), _asst("final")],  # second, then stable
    ]
    box = {"i": 0}

    def records_fn():
        i = min(box["i"], len(states) - 1)
        box["i"] += 1
        return states[i]

    events = []
    result = bridge_response(
        events.append, records_fn, start_index=1,  # skip the injected user prompt
        idle_rounds=2, max_rounds=50, sleep=lambda _s: None, poll=0,
    )
    assert [(e["kind"], e["payload"]["text"]) for e in events] == [
        ("assistant", "thinking"),
        ("assistant", "final"),
    ]
    assert result == "thinking\n\nfinal"


def test_bridge_times_out_without_assistant():
    def records_fn():
        return [_user("p")]  # never grows, no assistant ever

    events = []
    result = bridge_response(
        events.append, records_fn, start_index=1,
        idle_rounds=2, max_rounds=5, sleep=lambda _s: None,
    )
    assert events == []
    assert result == ""


def test_transcript_messages_maps_user_and_assistant():
    recs = [_user("q1"), _asst("a1"), _tool(), _asst("a2")]
    assert transcript_messages(recs) == [
        {"role": "user", "text": "q1"},
        {"role": "assistant", "text": "a1"},
        {"role": "assistant", "text": "a2"},  # tool_use block skipped (no text)
    ]
