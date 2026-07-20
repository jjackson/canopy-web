"""Read the recent message tail of a live emdash session's Claude transcript.

Phase B of the emdash session controller (docs/superpowers/specs/
2026-07-16-emdash-session-controller-design.md). STDLIB ONLY — the runner is
Django-free and cannot import apps.session_sharing.parser; this is the runner's
own minimal tail reader (user/assistant text for the last ~8 messages), not the
full ParsedTurn model the server uses.

emdash stores no conversation content in emdash4.db (the `messages` table is
empty); the content lives in Claude Code's transcript .jsonl under
~/.claude/projects/<encoded-worktree>/<session>.jsonl. There is no session id or
path in the DB, so the transcript is resolved by CONVENTION:

    worktree  = ~/emdash/worktrees/<repo>/emdash/<task>[-<suffix>]   (see below)
    proj dir  = ~/.claude/projects/<worktree with '/' and '.' -> '-'>
    file      = newest *.jsonl in that dir

The convention has two real-world wrinkles the naive path missed (both verified
against the live fleet, 2026-07-20): emdash appends a short random de-dupe suffix
to the worktree dir name (`-cysov`), and the layout is not uniform — some
worktrees sit at `<repo>/<task>` with no `emdash` segment. `resolve_transcript`
handles both by prefix-globbing each candidate base and accepting a `-<suffix>`
tail; the prefix stays anchored at the parent segment so one task can't grab
another's transcript.

A wrong path is a silent wrong-answer, so resolution returns None rather than
guess. Nothing here raises: a missing dir, unreadable file, or malformed line
degrades to an empty tail with a reason string, so the poll tick survives.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_MSG_CHARS = 2000
# Only the last few messages are ever shown, so read at most this many bytes from
# the END of the transcript rather than the whole file — a long session's .jsonl can
# be tens of MB, and the runner reads several of them on every poll tick (top-K).
TAIL_BYTES = 256 * 1024

# emdash appends a short random suffix to a worktree dir name to de-dupe it
# (e.g. the task "ace-nutrition-demo-9619-0720-1352" lives in a worktree dir
# "...-1352-cysov"). The Claude transcript project dir therefore ends in the
# task name OR the task name + "-<suffix>". This matches that trailing suffix.
_SUFFIX_RE = re.compile(r"-[0-9a-z]+$")


def encode_project_dir(worktree: Path) -> str:
    """Claude Code's ~/.claude/projects/<name> encoding: '/' and '.' -> '-'."""
    return str(worktree).replace("/", "-").replace(".", "-")


def _worktree_bases(repo: str, task: str, home: Path) -> list[Path]:
    """Candidate worktree paths for (repo, task). Verified against the live fleet
    (2026-07-20): most agents nest under `<repo>/emdash/<task>`, but some worktrees
    (e.g. echo's) sit directly at `<repo>/<task>` with no `emdash` segment. Try both;
    a wrong guess simply doesn't match a project dir and degrades to no transcript."""
    root = home / "emdash" / "worktrees" / repo
    return [root / "emdash" / task, root / task]


def resolve_transcript(repo: str, task: str, *, home: Path, claude_home: Path) -> Path | None:
    """Newest transcript .jsonl for (repo, task), or None.

    Resolves by emdash's worktree convention, tolerant of two real-world facts the
    original naive path missed: worktree dirs carry a random de-dupe suffix, and the
    layout isn't uniform (see `_worktree_bases`). For each candidate base we glob the
    encoded prefix and accept a project dir that is the exact encoding OR the encoding
    plus a `-<suffix>` tail, then take the newest .jsonl across all matches. A wrong
    guess returns None (empty tail), never a wrong transcript from an unrelated task —
    the prefix is anchored at the parent segment, so `mobile` can't match `alt-mobile`.
    """
    if not repo or not task or not claude_home.is_dir():
        return None
    candidates: list[Path] = []
    for base in _worktree_bases(repo, task, home):
        prefix = encode_project_dir(base)
        for proj_dir in claude_home.glob(prefix + "*"):
            if not proj_dir.is_dir():
                continue
            rest = proj_dir.name[len(prefix):]
            if rest == "" or _SUFFIX_RE.fullmatch(rest):
                candidates.extend(proj_dir.glob("*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _extract_text(content) -> str:
    """Human-readable text of a Claude message `content` (str or block list)."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "tool_use":
            parts.append(f"[tool: {block.get('name', 'unknown')}]")
        elif btype == "tool_result":
            parts.append(f"[result: {str(block.get('content', ''))[:200]}]")
    return " ".join(p for p in parts if p).strip()


def read_recent_messages(path: Path, limit: int = 8) -> list[dict]:
    """Last `limit` user/assistant messages as [{"role", "text"}], oldest→newest.

    Never raises: an unreadable file yields []; a malformed line is skipped.
    Reads only the last TAIL_BYTES of the file (the tail is all we need); if that
    cuts the first line mid-JSON, json.loads skips it — harmless, since we only want
    complete recent messages.
    """
    try:
        with path.open("rb") as f:
            size = f.seek(0, 2)
            f.seek(max(0, size - TAIL_BYTES))
            raw = f.read()
    except OSError:
        return []
    lines = raw.decode("utf-8", errors="replace").splitlines()
    msgs: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("isSidechain"):
            continue
        kind = payload.get("type")
        if kind not in ("user", "assistant"):
            continue
        message = payload.get("message")
        content = message.get("content", "") if isinstance(message, dict) else ""
        text = _extract_text(content)
        if text:
            msgs.append({"role": kind, "text": text[:MAX_MSG_CHARS]})
    return msgs[-limit:]


def session_tail(
    repo: str,
    task: str,
    *,
    limit: int = 8,
    home: Path | None = None,
    claude_home: Path | None = None,
) -> tuple[list[dict], str]:
    """(messages, reason). reason == "" on success. NEVER raises — see module docstring."""
    home = home or Path.home()
    claude_home = claude_home or (home / ".claude" / "projects")
    try:
        path = resolve_transcript(repo, task, home=home, claude_home=claude_home)
    except Exception:  # noqa: BLE001 — a fragile-half failure must not crash the tick
        logger.debug("transcript resolve failed for %s/%s", repo, task, exc_info=True)
        return [], "resolve-error"
    if path is None:
        return [], "no-transcript"
    msgs = read_recent_messages(path, limit=limit)
    if not msgs:
        return [], "empty-transcript"
    return msgs, ""


def attach_recent_tail(
    sessions: list[dict],
    *,
    count: int = 8,
    limit: int = 8,
    home: Path | None = None,
    claude_home: Path | None = None,
) -> None:
    """Fill recent_messages on the first `count` sessions (the most-recently-active,
    since emdash.list_open_sessions returns newest-first) — the ones the phone shows
    at the top of the list, so each has a glanceable tail without a round trip. In
    place, best-effort, never raises; the bounded tail read keeps K reads/tick cheap.

    `count` caps how many transcripts are read per tick; `limit` caps messages per
    session. Sessions past `count`, or with no resolvable transcript, carry [].
    """
    for s in sessions[:count]:
        msgs, _reason = session_tail(
            s.get("project", ""), s.get("emdash_task", ""),
            limit=limit, home=home, claude_home=claude_home,
        )
        s["recent_messages"] = msgs
