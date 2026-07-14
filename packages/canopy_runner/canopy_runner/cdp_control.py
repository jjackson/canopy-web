"""Python wrapper over the emdash CDP control sidecar (Node + playwright-core).

The runner drives emdash through its real UI over CDP — the sanctioned path that
supersedes DB injection + app patching. This module shells out to
`cdp/emdash_control.mjs`; keep the Python side thin. One-time setup:
`cd canopy_runner/cdp && npm install`.
"""
from __future__ import annotations

import getpass
import json
import socket
import subprocess
from pathlib import Path

SIDECAR = Path(__file__).parent / "cdp" / "emdash_control.mjs"


class CDPError(Exception):
    """emdash CDP control failed — often "task not present" (reuse should fall back
    to create) or "cannot connect" (emdash not launched with the debug port)."""


def host_id() -> str:
    """Stable macOS user@hostname for this account — the ownership key that decides
    whether a live emdash session is reusable (emdash is per-macOS-account)."""
    return f"{getpass.getuser()}@{socket.gethostname()}"


def _run(command: str, args: dict, *, node: str = "node", timeout: int = 90) -> dict:
    try:
        proc = subprocess.run(
            [node, str(SIDECAR), command, json.dumps(args)],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise CDPError("node not found — install Node.js and run "
                       "`cd canopy_runner/cdp && npm install`") from exc
    except subprocess.TimeoutExpired as exc:
        raise CDPError(f"emdash CDP '{command}' timed out after {timeout}s") from exc
    raw = (proc.stdout or "").strip()
    try:
        data = json.loads(raw) if raw else {}
    except ValueError as exc:
        raise CDPError(
            f"emdash CDP '{command}' returned non-JSON: {raw[:200]!r} "
            f"stderr={proc.stderr[:200]!r}"
        ) from exc
    if not data.get("ok"):
        raise CDPError(data.get("error") or proc.stderr.strip() or f"emdash CDP '{command}' failed")
    return data


def list_tasks(*, port: int = 9222) -> dict:
    """{tasks:[names], projects:[names]} currently visible in emdash."""
    return _run("list", {"port": port})


def create_task(project: str, prompt: str, *, task_name: str = "", port: int = 9222) -> dict:
    """Create a NEW emdash task under `project` with `prompt` as the initial message.
    Pass `task_name` for a deterministic, reusable name (recommended — the auto-name
    diff is unreliable under sidebar virtualization). Returns {..., "task": name}."""
    args = {"port": port, "project": project, "prompt": prompt}
    if task_name:
        args["taskName"] = task_name
    return _run("create", args)


def open_and_send(task: str, text: str, *, port: int = 9222) -> dict:
    """REUSE: open an existing task and send `text` into its live terminal.
    Raises CDPError if the task isn't present (caller falls back to create+rehydrate)."""
    return _run("open-send", {"port": port, "task": task, "text": text})
