"""Control-plane HTTP client. stdlib urllib; every call is short and synchronous."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

TIMEOUT = 10


class ClientError(Exception):
    pass


class Client:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
        url = f"{self.base_url}/api/harness{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                status = resp.status
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                error_body = exc.read()[:200]
            except Exception:
                error_body = b"(could not read error body)"
            raise ClientError(f"{method} {path} -> {exc.code}: {error_body!r}") from exc
        except urllib.error.URLError as exc:
            raise ClientError(f"{method} {path} -> {exc.reason}") from exc
        if status == 204 or not raw:
            return status, None
        return status, json.loads(raw)

    def heartbeat(self, runner_id: str, active_turn_ids: list[str], degraded: bool = False,
                  note: str = "", host: str = "") -> dict:
        _, payload = self._call(
            "POST",
            f"/runners/{runner_id}/heartbeat",
            {"active_turn_ids": active_turn_ids, "degraded": degraded, "note": note, "host": host},
        )
        return payload or {}

    def resolve_session(self, runner_id: str, agent_slug: str, thread_key: str) -> dict:
        """Ask the control plane whether THIS runner can reuse an existing emdash
        session for (agent, thread) or must spawn fresh + rehydrate. See SessionLink."""
        _, payload = self._call(
            "POST", f"/runners/{runner_id}/resolve-session",
            {"agent_slug": agent_slug, "thread_key": thread_key},
        )
        return payload or {}

    def record_session(self, runner_id: str, agent_slug: str, thread_key: str, *,
                       emdash_task_id: str = "", session_id: str = "",
                       agent_task_ext_id: str | None = None, summary: str | None = None) -> dict:
        """Record/point the durable thread link at THIS runner's live session."""
        _, payload = self._call(
            "POST", f"/runners/{runner_id}/record-session",
            {"agent_slug": agent_slug, "thread_key": thread_key,
             "emdash_task_id": emdash_task_id, "session_id": session_id,
             "agent_task_ext_id": agent_task_ext_id, "summary": summary},
        )
        return payload or {}

    def claim(self, runner_id: str, paused_agents: list[str] | None = None) -> dict | None:
        # paused_agents (per-agent pause) → server skips those agents' queued turns.
        path = f"/runners/{runner_id}/claim"
        if paused_agents:
            from urllib.parse import urlencode
            path += "?" + urlencode({"paused": ",".join(sorted(paused_agents))})
        status, payload = self._call("POST", path)
        return payload if status == 200 else None

    def post_events(self, turn_id: str, events: list[dict]) -> None:
        self._call("POST", f"/turns/{turn_id}/events", {"events": events})

    def enqueue_turn(self, agent_slug: str, origin: str, idempotency_key: str, *,
                     prompt: str = "", origin_ref: dict | None = None,
                     routing: str = "prefer_local") -> dict:
        """Enqueue a turn (idempotent on idempotency_key — safe to re-enqueue the same
        email). Used by the deterministic inbox/slack triggers."""
        _, payload = self._call("POST", "/turns/", {
            "agent_slug": agent_slug, "origin": origin, "idempotency_key": idempotency_key,
            "prompt": prompt, "origin_ref": origin_ref or {}, "routing": routing,
        })
        return payload or {}

    def start(self, turn_id: str, session_id: str = "") -> None:
        self._call("POST", f"/turns/{turn_id}/start", {"session_id": session_id})

    def finish(self, turn_id: str, note: str = "") -> None:
        self._call("POST", f"/turns/{turn_id}/finish", {"status": "done", "result_note": note})

    def fail_turn(self, turn_id: str, note: str) -> None:
        self._call("POST", f"/turns/{turn_id}/finish", {"status": "failed", "result_note": note})

    def get_turn(self, turn_id: str) -> dict:
        _, payload = self._call("GET", f"/turns/{turn_id}")
        return payload or {}
