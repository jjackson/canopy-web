"""Bridge an emdash session's live response back into the harness ledger.

The laptop runner injects a chat prompt into an emdash session and then TAILS that
session's Claude Code transcript (.jsonl), posting each new assistant TEXT block as
an `assistant` TurnEvent — which the chat SessionConsumer translates to chat.stream_*
so the website streams the reply. This is the piece the normal agent/project path
deliberately omits (there the work just continues in the visible emdash session).

Completion is IDLE-based: emdash/Claude Code write no "turn done" marker to the
transcript, so we finish when the file stops growing for a few polls AFTER the
assistant has spoken (or a hard timeout). Pure + injectable (records_fn / sleep) so
the loop unit-tests without real files or a real clock.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


def _assistant_text(content) -> str:
    """The assistant's spoken output — TEXT blocks only (tool_use blocks are skipped
    for the v1 bridge; the website shows the reply, not the tool calls)."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = [
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    return "".join(parts).strip()


def read_records(path) -> list[dict]:
    """Every JSONL record in the transcript, best-effort (never raises)."""
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return []
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def new_assistant_texts(records: list[dict], since: int) -> list[str]:
    """Assistant TEXT messages in records[since:], oldest->newest, non-empty only."""
    texts: list[str] = []
    for rec in records[since:]:
        if rec.get("type") != "assistant":
            continue
        msg = rec.get("message")
        content = msg.get("content", "") if isinstance(msg, dict) else ""
        t = _assistant_text(content)
        if t:
            texts.append(t)
    return texts


def _user_text(content) -> str:
    """A user record's text — a bare string, or the text blocks of a content list."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
    return ""


def transcript_messages(records: list[dict]) -> list[dict]:
    """The full transcript as chronological {"role","text"} rows — user + assistant
    text only (tool blocks skipped, matching the v1 bridge). Drives on-demand
    backfill of a local session's history into server Message rows."""
    out: list[dict] = []
    for rec in records:
        kind = rec.get("type")
        msg = rec.get("message")
        content = msg.get("content", "") if isinstance(msg, dict) else ""
        if kind == "user":
            t = _user_text(content)
            if t:
                out.append({"role": "user", "text": t})
        elif kind == "assistant":
            t = _assistant_text(content)
            if t:
                out.append({"role": "assistant", "text": t})
    return out


def bridge_response(
    post_event: Callable[[dict], None],
    records_fn: Callable[[], list[dict]],
    *,
    start_index: int,
    idle_rounds: int = 6,
    max_rounds: int = 1200,
    sleep: Callable[[float], None],
    poll: float = 0.5,
) -> str:
    """Tail the transcript from `start_index`, posting each new assistant TEXT as an
    `assistant` event via `post_event`. Finish when no new records arrive for
    `idle_rounds` consecutive polls (after >=1 assistant text), or `max_rounds` hit.
    Returns the concatenated assistant text (for the turn's finish note)."""
    seen = start_index
    got_assistant = False
    idle = 0
    collected: list[str] = []
    for _ in range(max_rounds):
        records = records_fn()
        if len(records) > seen:
            for text in new_assistant_texts(records, seen):
                post_event({"kind": "assistant", "payload": {"text": text}})
                collected.append(text)
                got_assistant = True
            seen = len(records)
            idle = 0
        elif got_assistant:
            idle += 1
            if idle >= idle_rounds:
                break
        sleep(poll)
    return "\n\n".join(collected)
