"""Runner config: one JSON file, stdlib only."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    base_url: str
    token: str
    runner_id: str
    emdash_db: str
    automation_ids: dict[str, str]
    expected_migration_id: int
    emdash_fingerprint: str = ""
    poll_seconds: int = 20
    heartbeat_seconds: int = 30
    state_path: str = ""
    # Executor: "cdp" drives emdash's real UI over CDP (create/reuse sessions —
    # the sanctioned path); "inject" is the legacy DB-injection path. cdp needs
    # emdash launched with --remote-debugging-port=<cdp_port> (see "Emdash CDP").
    executor: str = "cdp"
    cdp_port: int = 9222
    inbox_poll_seconds: int = 300
    # {agent_slug: {"account": "<mailbox>", "client": "<gog client>"}} — the
    # deterministic email trigger polls these and enqueues email-origin turns.
    mailboxes: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Config":
        raw = json.loads(Path(path).read_text())
        token = raw["token"]
        if token.startswith("@"):
            token = Path(token[1:]).expanduser().read_text().strip()
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in raw.items() if k in known}
        kwargs["token"] = token
        cfg = cls(**kwargs)
        if not cfg.state_path:
            cfg.state_path = str(Path(path).with_name("runner-state.json"))
        return cfg
