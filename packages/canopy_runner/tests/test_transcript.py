import json
from pathlib import Path

from canopy_runner import transcript


def test_encode_project_dir_replaces_slash_and_dot():
    wt = Path("/Users/j/emdash/worktrees/canopy-web/emdash/mobile-kn063")
    assert transcript.encode_project_dir(wt) == (
        "-Users-j-emdash-worktrees-canopy-web-emdash-mobile-kn063"
    )
    # dots also become dashes (Claude Code's convention)
    assert transcript.encode_project_dir(Path("/a/b.c")) == "-a-b-c"


def _write_transcript(claude_home: Path, worktree: Path, lines: list[dict]) -> Path:
    proj = claude_home / transcript.encode_project_dir(worktree)
    proj.mkdir(parents=True)
    f = proj / "sess.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines), "utf-8")
    return f


def test_session_tail_reads_recent_user_and_assistant_text(tmp_path):
    home = tmp_path / "home"
    claude_home = home / ".claude" / "projects"
    worktree = home / "emdash" / "worktrees" / "canopy-web" / "emdash" / "ddd"
    _write_transcript(claude_home, worktree, [
        {"type": "system", "subtype": "init", "session_id": "s1"},
        {"type": "user", "message": {"content": "fix the header"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "On it."}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit"}]}},
    ])
    msgs, reason = transcript.session_tail(
        "canopy-web", "ddd", limit=8, home=home, claude_home=claude_home
    )
    assert reason == ""
    assert msgs[0] == {"role": "user", "text": "fix the header"}
    assert msgs[1] == {"role": "assistant", "text": "On it."}
    assert msgs[2] == {"role": "assistant", "text": "[tool: Edit]"}


def test_session_tail_limits_to_last_n(tmp_path):
    home = tmp_path / "home"
    claude_home = home / ".claude" / "projects"
    worktree = home / "emdash" / "worktrees" / "canopy-web" / "emdash" / "ddd"
    lines = [{"type": "system", "subtype": "init", "session_id": "s1"}]
    for i in range(20):
        lines.append({"type": "user", "message": {"content": f"m{i}"}})
    _write_transcript(claude_home, worktree, lines)
    msgs, reason = transcript.session_tail(
        "canopy-web", "ddd", limit=8, home=home, claude_home=claude_home
    )
    assert reason == ""
    assert [m["text"] for m in msgs] == [f"m{i}" for i in range(12, 20)]


def test_session_tail_missing_transcript_returns_reason_not_raise(tmp_path):
    home = tmp_path / "home"
    claude_home = home / ".claude" / "projects"
    msgs, reason = transcript.session_tail(
        "canopy-web", "nope", limit=8, home=home, claude_home=claude_home
    )
    assert msgs == []
    assert reason == "no-transcript"


def test_read_recent_messages_skips_malformed_lines(tmp_path):
    f = tmp_path / "x.jsonl"
    f.write_text(
        '{"type":"user","message":{"content":"ok"}}\n'
        "NOT JSON\n"
        '{"type":"assistant","message":{"content":[{"type":"text","text":"hi"}]}}\n',
        "utf-8",
    )
    msgs = transcript.read_recent_messages(f, limit=8)
    assert [m["text"] for m in msgs] == ["ok", "hi"]


def test_text_truncated_to_max(tmp_path):
    f = tmp_path / "x.jsonl"
    f.write_text(json.dumps({"type": "user", "message": {"content": "z" * 5000}}), "utf-8")
    msgs = transcript.read_recent_messages(f, limit=8)
    assert len(msgs[0]["text"]) == transcript.MAX_MSG_CHARS
