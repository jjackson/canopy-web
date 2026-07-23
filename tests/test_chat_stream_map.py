"""TurnEvent -> canonical chat.* frame translation (pure)."""
from __future__ import annotations

from apps.canopy_sessions.stream_map import turn_event_to_frames


def _rid(seq):
    return f"m:{seq}"


def test_assistant_maps_to_start_and_complete():
    frames = turn_event_to_frames(
        {"seq": 5, "kind": "assistant", "payload": {"text": "hello"}, "ts": "t"}, _rid)
    assert [f["event"] for f in frames] == ["chat.stream_start", "chat.stream_complete"]
    assert frames[0]["data"]["message_id"] == "m:5"
    assert frames[1]["data"]["plaintext"] == "hello"


def test_tool_events_map():
    assert turn_event_to_frames(
        {"seq": 1, "kind": "tool_start", "payload": {"name": "Bash"}, "ts": "t"}, _rid
    )[0]["event"] == "chat.tool_use"
    assert turn_event_to_frames(
        {"seq": 2, "kind": "tool_end", "payload": {"ok": True}, "ts": "t"}, _rid
    )[0]["event"] == "chat.tool_result"


def test_status_and_heartbeat_are_silent():
    assert turn_event_to_frames({"seq": 1, "kind": "status", "payload": {"status": "running"}, "ts": "t"}, _rid) == []
    assert turn_event_to_frames({"seq": 1, "kind": "heartbeat", "payload": {}, "ts": "t"}, _rid) == []


def test_error_maps_to_stream_error():
    frames = turn_event_to_frames({"seq": 9, "kind": "error", "payload": {"detail": "boom"}, "ts": "t"}, _rid)
    assert frames[0]["event"] == "chat.stream_error"
    assert frames[0]["data"]["detail"] == "boom"
