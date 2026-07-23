"""Translate a TurnEvent ledger row into canonical ace-web chat.* stream frames.

Pure and Django-free: the consumer supplies a `resolve_message_id(seq) -> str`
callback (a projected Message id, or a synthetic id) and this returns the client
frames for one ledger event. The ledger stays the source of truth; this is only a
presentation mapping.

Today the stub runner emits a whole `assistant` event (no token deltas), so an
assistant event maps to stream_start + stream_complete. A future delta-emitting
runner would instead yield incremental `chat.delta` frames — out of scope here,
and the client reducer already tolerates either.
"""
from __future__ import annotations

from typing import Callable


def turn_event_to_frames(evt: dict, resolve_message_id: Callable[[int], str]) -> list[dict]:
    kind = evt.get("kind")
    seq = evt.get("seq")
    payload = evt.get("payload") or {}

    if kind == "assistant":
        mid = resolve_message_id(seq)
        return [
            {"event": "chat.stream_start", "data": {"message_id": mid, "turn_index": seq}},
            {"event": "chat.stream_complete", "data": {"message_id": mid, "plaintext": payload.get("text", "")}},
        ]
    if kind == "tool_start":
        mid = resolve_message_id(seq)
        return [{"event": "chat.tool_use",
                 "data": {"parent_message_id": None, "tool_message_id": mid, "block": payload}}]
    if kind in ("tool_end", "tool_result"):
        mid = resolve_message_id(seq)
        return [{"event": "chat.tool_result",
                 "data": {"parent_message_id": None, "tool_message_id": mid, "block": payload}}]
    if kind == "error":
        mid = resolve_message_id(seq)
        return [{"event": "chat.stream_error",
                 "data": {"message_id": mid, "detail": payload.get("detail") or payload.get("text", "error")}}]
    # status / heartbeat / question / approval carry no client-visible stream frame.
    return []
