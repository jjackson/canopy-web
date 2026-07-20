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

    worktree  = ~/emdash/worktrees/<repo>/emdash/<task>
    proj dir  = ~/.claude/projects/<worktree with '/' and '.' -> '-'>
    file      = newest *.jsonl in that dir

A wrong path is a silent wrong-answer, so resolution returns None rather than
guess. Nothing here raises: a missing dir, unreadable file, or malformed line
degrades to an empty tail with a reason string, so the poll tick survives.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_MSG_CHARS = 2000


def encode_project_dir(worktree: Path) -> str:
    """Claude Code's ~/.claude/projects/<name> encoding: '/' and '.' -> '-'."""
    return str(worktree).replace("/", "-").replace(".", "-")


def resolve_transcript(repo: str, task: str, *, home: Path, claude_home: Path) -> Path | None:
    """Newest .jsonl for (repo, task) by emdash's worktree convention, or None."""
    if not repo or not task:
        return None
    worktree = home / "emdash" / "worktrees" / repo / "emdash" / task
    proj_dir = claude_home / encode_project_dir(worktree)
    if not proj_dir.is_dir():
        return None
    jsonls = sorted(proj_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonls[0] if jsonls else None


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
    """
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return []
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
    limit: int = 8,
    home: Path | None = None,
    claude_home: Path | None = None,
) -> None:
    """Eagerly fill recent_messages on the MOST-RECENTLY-ACTIVE session (index 0).

    That is the session the supervisor is most likely to open ("this session"),
    so its click-in is instant with no extra round trip. In place, best-effort,
    never raises. Other sessions carry [] until Task 4 (watch) fills them.
    """
    if not sessions:
        return
    top = sessions[0]
    msgs, _reason = session_tail(
        top.get("project", ""), top.get("emdash_task", ""),
        limit=limit, home=home, claude_home=claude_home,
    )
    top["recent_messages"] = msgs
