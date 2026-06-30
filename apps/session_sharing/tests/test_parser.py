"""Round-trip tests for the .jsonl transcript parser."""
from __future__ import annotations

import json
from pathlib import Path

from apps.session_sharing.parser import parse_session_file


def _write_jsonl(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "session.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def test_parses_init_user_assistant_and_tools(tmp_path):
    rows = [
        {"type": "system", "subtype": "init", "session_id": "abc-123"},
        {"type": "user", "message": {"content": "hello there"}},
        {
            "type": "assistant",
            "message": {
                "id": "m1",
                "content": [
                    {"type": "text", "text": "Hi! "},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "content": "file1\nfile2"},
                ]
            },
        },
        {
            "type": "assistant",
            "message": {"id": "m2", "content": [{"type": "text", "text": "Done."}]},
        },
    ]
    parsed = parse_session_file(_write_jsonl(tmp_path, rows))

    assert parsed.cli_session_id == "abc-123"
    roles = [t.role for t in parsed.turns]
    assert roles == ["user", "assistant", "tool_use", "tool_result", "assistant"]
    assert parsed.turns[0].plaintext == "hello there"
    assert parsed.turns[1].plaintext == "Hi! "
    assert parsed.turns[2].plaintext == "Tool: Bash"
    assert "file1" in parsed.turns[3].plaintext
    assert parsed.turns[4].plaintext == "Done."


def test_skips_invalid_json_lines(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(
        '{"type": "system", "subtype": "init", "session_id": "x"}\n'
        "this is not json\n"
        '{"type": "assistant", "message": {"id": "m", "content": [{"type": "text", "text": "ok"}]}}\n'
    )
    parsed = parse_session_file(p)
    assert parsed.cli_session_id == "x"
    assert [t.role for t in parsed.turns] == ["assistant"]
    assert parsed.line_count == 3
