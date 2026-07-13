import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from canopy_runner.config import Config
from canopy_runner.main import run_once

AUTOMATION_ID = "auto-1"


@pytest.fixture()
def db(tmp_path: Path) -> str:
    path = tmp_path / "emdash4.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE __drizzle_migrations (id INTEGER PRIMARY KEY, hash TEXT, created_at INTEGER);
        INSERT INTO __drizzle_migrations (id, hash, created_at) VALUES (19, 'h', 0);
        CREATE TABLE automations (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, task_config TEXT, project_id TEXT,
          enabled INTEGER DEFAULT 1 NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
          trigger_config TEXT, conversation_config TEXT, deleted_at INTEGER
        );
        CREATE TABLE automation_runs (
          id TEXT PRIMARY KEY, automation_id TEXT NOT NULL, scheduled_at INTEGER, deadline_at INTEGER,
          started_at INTEGER, task_created_at INTEGER, launched_at INTEGER, finished_at INTEGER,
          status TEXT NOT NULL, error TEXT, trigger_kind TEXT NOT NULL,
          trigger_config_snapshot TEXT DEFAULT '{}' NOT NULL,
          conversation_config_snapshot TEXT DEFAULT '{}' NOT NULL,
          task_config_snapshot TEXT, generated_task_name TEXT
        );
        CREATE TABLE tasks (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
          type TEXT DEFAULT 'task' NOT NULL, automation_run_id TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO automations (id, name, task_config, project_id, enabled, created_at, updated_at, conversation_config) "
        "VALUES (?, 'canopy-turns', ?, 'proj-1', 1, 0, 0, ?)",
        (
            AUTOMATION_ID,
            json.dumps({"version": "1", "taskConfig": {"version": "1", "name": "t"}, "workspaceConfig": {}}),
            json.dumps({"prompt": "/canopy:drain-turn echo", "provider": "claude", "autoApprove": False, "type": "pty"}),
        ),
    )
    conn.commit()
    conn.close()
    return str(path)


class FakeClient:
    def __init__(self, turns=None):
        self.turns = list(turns or [])
        self.events = []
        self.heartbeats = []
        self.failed = []

    def heartbeat(self, runner_id, active_turn_ids, degraded=False, note=""):
        self.heartbeats.append((runner_id, list(active_turn_ids), degraded, note))
        return {"status": "degraded" if degraded else "online"}

    def claim(self, runner_id):
        return self.turns.pop(0) if self.turns else None

    def post_events(self, turn_id, events):
        self.events.append((turn_id, events))

    def fail_turn(self, turn_id, note):
        self.failed.append((turn_id, note))


def _cfg(db, tmp_path):
    return Config(
        base_url="http://x", token="t", runner_id="r-1", emdash_db=db,
        automation_ids={"echo": AUTOMATION_ID}, expected_migration_id=19,
        state_path=str(tmp_path / "state.json"),
    )


def test_idle_when_no_work(db, tmp_path):
    client = FakeClient()
    assert run_once(_cfg(db, tmp_path), client) == "idle"
    assert client.heartbeats  # heartbeat always sent


def test_claim_injects_run_and_reports_events(db, tmp_path):
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    result = run_once(_cfg(db, tmp_path), client)
    assert result == "injected:t-1"
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM automation_runs").fetchone()[0] == 1
    kinds = [e["kind"] for _, evs in client.events for e in evs]
    assert "status" in kinds  # injected event posted
    # state file records the active turn for crash-safe rehydration
    state = json.loads(Path(_cfg(db, tmp_path).state_path).read_text())
    assert "t-1" in state["active"]


def test_unknown_agent_fails_turn(db, tmp_path):
    client = FakeClient(turns=[{"id": "t-2", "agent_slug": "eva", "status": "claimed"}])
    result = run_once(_cfg(db, tmp_path), client)
    assert result == "failed:t-2"
    assert client.failed and client.failed[0][0] == "t-2"


def test_schema_drift_goes_degraded_and_never_writes(db, tmp_path):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO __drizzle_migrations (id, hash, created_at) VALUES (20, 'x', 0)")
    conn.commit(); conn.close()
    client = FakeClient(turns=[{"id": "t-3", "agent_slug": "echo", "status": "claimed"}])
    result = run_once(_cfg(db, tmp_path), client)
    assert result == "degraded"
    assert client.heartbeats[-1][2] is True  # degraded flag
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM automation_runs").fetchone()[0] == 0


def test_promotes_task_on_followup_pass(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    run_once(cfg, client)  # inject
    state = json.loads(Path(cfg.state_path).read_text())
    run_id = state["active"]["t-1"]["emdash_run_id"]
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tasks (id, project_id, name, status, type, automation_run_id) "
        "VALUES ('task-1', 'proj-1', 'fruity', 'in_progress', 'automation-run', ?)", (run_id,)
    )
    conn.commit(); conn.close()
    result = run_once(cfg, client)  # follow-up pass sees the task
    assert result == "promoted:task-1"
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT type FROM tasks WHERE id='task-1'").fetchone()[0] == "task"
