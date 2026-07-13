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

    def heartbeat(self, runner_id: str, active_turn_ids: list[str], degraded: bool = False, note: str = "") -> dict:
        _, payload = self._call(
            "POST",
            f"/runners/{runner_id}/heartbeat",
            {"active_turn_ids": active_turn_ids, "degraded": degraded, "note": note},
        )
        return payload or {}

    def claim(self, runner_id: str) -> dict | None:
        status, payload = self._call("POST", f"/runners/{runner_id}/claim")
        return payload if status == 200 else None

    def post_events(self, turn_id: str, events: list[dict]) -> None:
        self._call("POST", f"/turns/{turn_id}/events", {"events": events})

    def fail_turn(self, turn_id: str, note: str) -> None:
        self._call("POST", f"/turns/{turn_id}/finish", {"status": "failed", "result_note": note})
