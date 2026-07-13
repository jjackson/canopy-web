import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from canopy_runner.emdash import (
    SchemaDrift,
    check_schema,
    find_task,
    inject_run,
    promote_task,
    run_status,
)

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


def test_check_schema_ok(db):
    check_schema(db, 19)  # no raise


def test_check_schema_drift_raises(db):
    with pytest.raises(SchemaDrift):
        check_schema(db, 18)


def test_inject_run_copies_snapshots(db):
    rid = str(uuid.uuid4())
    inject_run(db, AUTOMATION_ID, rid, task_name="canopy-turn-echo")
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, trigger_kind, conversation_config_snapshot, generated_task_name "
        "FROM automation_runs WHERE id=?", (rid,)
    ).fetchone()
    assert row[0] == "queued" and row[1] == "manual"
    assert json.loads(row[2])["prompt"] == "/canopy:drain-turn echo"
    assert row[3] == "canopy-turn-echo"
    assert run_status(db, rid) == "queued"


def test_inject_refuses_unknown_automation(db):
    with pytest.raises(ValueError):
        inject_run(db, "nope", str(uuid.uuid4()), task_name="x")


def test_find_and_promote_task(db):
    rid = str(uuid.uuid4())
    inject_run(db, AUTOMATION_ID, rid, task_name="x")
    assert find_task(db, rid) is None
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tasks (id, project_id, name, status, type, automation_run_id) "
        "VALUES ('task-1', 'proj-1', 'fruity', 'in_progress', 'automation-run', ?)", (rid,)
    )
    conn.commit(); conn.close()
    task = find_task(db, rid)
    assert task == {"id": "task-1", "name": "fruity", "status": "in_progress", "type": "automation-run"}
    promote_task(db, "task-1")
    assert find_task(db, rid)["type"] == "task"
