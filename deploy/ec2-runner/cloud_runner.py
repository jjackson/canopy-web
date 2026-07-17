#!/usr/bin/env python3
"""Canopy cloud runner — a headless `kind=cloud` executor for EC2.

Self-contained (stdlib only) on purpose: the emdash-coupled packages/canopy_runner
drives a GUI over CDP, which is wrong for a headless box. This pairs a cloud runner,
claims harness Turns, runs `claude -p` (stream-json) on the turn's prompt, streams
the assistant/tool output into the TurnEvent ledger, and finishes the turn.

Config comes from the environment (see deploy/ec2-runner/README.md):
  CANOPY_BASE_URL   e.g. https://labs.connect.dimagi.com/canopy
  CANOPY_TOKEN      a canopy-web Personal Access Token (Bearer)
  RUNNER_NAME       display name (default: this hostname)
  RUNNER_CAPS       JSON, e.g. {"projects":["canopy-web"]} or {"agents":["echo"]}
  RUNNER_WORKSPACE  optional workspace slug (defaults to the token's default)
  CLAUDE_BIN        path to the claude binary (default: claude)
  WORK_DIR          where claude runs (default: /tmp/canopy-runner-work)
  POLL_SECONDS      idle poll interval (default: 15)
  STATE_FILE        runner-id cache (default: ~/.canopy-cloud-runner.json)
`claude` authenticates from CLAUDE_CODE_OAUTH_TOKEN in its own environment.
"""
from __future__ import annotations

import json
import os
import pathlib
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("CANOPY_BASE_URL", "").rstrip("/")
TOKEN = os.environ.get("CANOPY_TOKEN", "")
RUNNER_NAME = os.environ.get("RUNNER_NAME") or f"cloud-{socket.gethostname()}"
RUNNER_CAPS = json.loads(os.environ.get("RUNNER_CAPS") or "{}")
RUNNER_WORKSPACE = os.environ.get("RUNNER_WORKSPACE", "")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
WORK_DIR = os.environ.get("WORK_DIR", "/tmp/canopy-runner-work")
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "15"))
STATE_FILE = pathlib.Path(os.environ.get("STATE_FILE", str(pathlib.Path.home() / ".canopy-cloud-runner.json")))

_stop = False


def _log(msg: str) -> None:
    print(f"[cloud-runner] {msg}", flush=True)


def _api(method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
    url = f"{BASE_URL}/api/harness{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        _log(f"{method} {path} -> {exc.code}: {raw[:300]!r}")
        return exc.code, None
    except urllib.error.URLError as exc:
        _log(f"{method} {path} -> URLError {exc.reason}")
        return 0, None


def pair_or_load() -> str:
    if STATE_FILE.exists():
        rid = json.loads(STATE_FILE.read_text()).get("runner_id")
        if rid:
            # Confirm it still exists (a heartbeat 404 means it was retired).
            status, _ = _api("POST", f"/runners/{rid}/heartbeat", {"active_turn_ids": []})
            if status == 200:
                _log(f"reusing runner {rid}")
                return rid
    body = {"name": RUNNER_NAME, "kind": "cloud", "capabilities": RUNNER_CAPS}
    if RUNNER_WORKSPACE:
        body["workspace"] = RUNNER_WORKSPACE
    status, payload = _api("POST", "/runners/", body)
    if status != 201 or not payload:
        _log(f"FATAL: could not pair runner (status={status}). Check CANOPY_BASE_URL/CANOPY_TOKEN.")
        sys.exit(1)
    rid = payload["id"]
    STATE_FILE.write_text(json.dumps({"runner_id": rid}))
    _log(f"paired new runner {rid} ({RUNNER_NAME}, caps={RUNNER_CAPS})")
    return rid


def run_claude(prompt: str, turn_id: str) -> tuple[bool, str]:
    """Run `claude -p` on the prompt, streaming stream-json events into the ledger.
    Returns (ok, final_text)."""
    workdir = pathlib.Path(WORK_DIR) / turn_id[:8]
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [
        CLAUDE_BIN, "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--dangerously-skip-permissions",
    ]
    _log(f"exec: claude -p (turn {turn_id[:8]}) in {workdir}")
    proc = subprocess.Popen(
        cmd, cwd=str(workdir), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    final_text = ""
    ok = True
    batch: list[dict] = []

    def flush():
        nonlocal batch
        if batch:
            _api("POST", f"/turns/{turn_id}/events", {"events": batch})
            batch = []

    for line in proc.stdout:  # type: ignore[union-attr]
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = evt.get("type")
        if etype == "assistant":
            for block in (evt.get("message", {}).get("content") or []):
                if block.get("type") == "text" and block.get("text"):
                    batch.append({"kind": "assistant", "payload": {"text": block["text"]}})
                elif block.get("type") == "tool_use":
                    batch.append({"kind": "tool_start", "payload": {"name": block.get("name", "")}})
        elif etype == "user":
            for block in (evt.get("message", {}).get("content") or []):
                if block.get("type") == "tool_result":
                    batch.append({"kind": "tool_end", "payload": {}})
        elif etype == "result":
            final_text = evt.get("result", "") or ""
            ok = not evt.get("is_error", False)
        if len(batch) >= 10:
            flush()
    proc.wait()
    flush()
    if proc.returncode != 0 and not final_text:
        ok = False
        final_text = (proc.stderr.read() if proc.stderr else "")[:500]
    return ok, final_text


def main() -> None:
    if not BASE_URL or not TOKEN:
        _log("FATAL: CANOPY_BASE_URL and CANOPY_TOKEN are required")
        sys.exit(1)
    runner_id = pair_or_load()
    _log(f"polling {BASE_URL} every {POLL_SECONDS}s")
    while not _stop:
        _api("POST", f"/runners/{runner_id}/heartbeat", {"active_turn_ids": []})
        status, turn = _api("POST", f"/runners/{runner_id}/claim")
        if status != 200 or not turn:
            time.sleep(POLL_SECONDS)
            continue
        turn_id = turn["id"]
        _log(f"claimed turn {turn_id[:8]} target={turn.get('target')}")
        _api("POST", f"/turns/{turn_id}/start", {"session_id": f"cloud-{turn_id[:8]}"})
        # keep the lease alive while claude runs
        _api("POST", f"/runners/{runner_id}/heartbeat", {"active_turn_ids": [turn_id]})
        try:
            ok, text = run_claude(turn.get("prompt", ""), turn_id)
        except Exception as exc:  # never let one turn kill the loop
            ok, text = False, f"runner error: {exc}"
        finish = "done" if ok else "failed"
        _api("POST", f"/turns/{turn_id}/finish", {"status": finish, "result_note": text[:2000]})
        _log(f"finished turn {turn_id[:8]}: {finish}")


def _handle_stop(*_a):
    global _stop
    _stop = True
    _log("stopping after current turn")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    main()
