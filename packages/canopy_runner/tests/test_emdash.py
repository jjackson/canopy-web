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
    task_state,
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
          archived_at TEXT,
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


def test_inject_run_is_idempotent_on_same_run_id(db):
    rid = str(uuid.uuid4())
    inject_run(db, AUTOMATION_ID, rid, task_name="first")
    # Simulate a runner retry after an ambiguous crash: same run_id, called again.
    inject_run(db, AUTOMATION_ID, rid, task_name="second")

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT generated_task_name FROM automation_runs WHERE id=?", (rid,)
    ).fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0][0] == "first"


def test_check_schema_raises_schemadrift_when_table_missing(tmp_path: Path):
    path = tmp_path / "no-migrations.db"
    conn = sqlite3.connect(path)
    conn.close()

    with pytest.raises(SchemaDrift):
        check_schema(str(path), 19)


def test_connections_are_closed(db, monkeypatch):
    """Every sqlite3.connect() made by the module must be closed, on both the
    read (run_status) and write (inject_run) paths."""
    real_connect = sqlite3.connect
    created: list["TrackingConnection"] = []
    closed: list["TrackingConnection"] = []

    class TrackingConnection:
        def __init__(self, real_conn):
            object.__setattr__(self, "_real", real_conn)

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __setattr__(self, name, value):
            setattr(self._real, name, value)

        def close(self):
            closed.append(self)
            self._real.close()

    def fake_connect(*args, **kwargs):
        wrapped = TrackingConnection(real_connect(*args, **kwargs))
        created.append(wrapped)
        return wrapped

    monkeypatch.setattr(sqlite3, "connect", fake_connect)

    rid = str(uuid.uuid4())
    inject_run(db, AUTOMATION_ID, rid, task_name="x")
    run_status(db, rid)

    assert len(created) >= 2
    assert len(closed) == len(created)


# --------------------------------------------------------------------------------------
# task_state — READ-ONLY existence truth for the reuse decision (see execute.execute_turn)
# --------------------------------------------------------------------------------------

def _add_task(db, name, *, archived_at=None, task_id=None):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tasks (id, project_id, name, status, archived_at) VALUES (?, 'proj-1', ?, 'in_progress', ?)",
        (task_id or str(uuid.uuid4()), name, archived_at),
    )
    conn.commit()
    conn.close()


def test_task_state_live(db):
    _add_task(db, "eva-org-research-790c-0715-1352")
    assert task_state(db, "eva-org-research-790c-0715-1352") == "live"


def test_task_state_archived(db):
    _add_task(db, "eva-org-research-790c-0715-1216", archived_at="2026-07-15T19:07:21.147Z")
    assert task_state(db, "eva-org-research-790c-0715-1216") == "archived"


def test_task_state_absent(db):
    assert task_state(db, "never-existed") == "absent"


def test_task_state_unknown_when_db_unreadable(tmp_path):
    """An unreadable/missing DB must NOT masquerade as 'absent' — that would be a false
    'gone' and duplicate a live session. The caller degrades to the CDP verdict instead."""
    assert task_state(str(tmp_path / "nope.db"), "anything") == "unknown"


def test_task_state_does_not_create_a_db_file(tmp_path):
    """sqlite3.connect() creates an empty file by default — don't litter emdash's dir."""
    missing = tmp_path / "nope.db"
    task_state(str(missing), "anything")
    assert not missing.exists()


def test_task_state_is_read_only_and_ungated_by_the_migration_pin(db):
    """Reads can't corrupt emdash, so unlike inject_run they are NOT behind the vetted
    pin — a drifted emdash must still be able to answer 'does this task exist?'."""
    conn = sqlite3.connect(db)
    conn.execute("UPDATE __drizzle_migrations SET id=999")
    conn.commit()
    conn.close()
    _add_task(db, "still-answerable")
    assert task_state(db, "still-answerable") == "live"


def test_task_state_prefers_the_newest_row_for_a_reused_name(db):
    """Task names aren't unique in emdash's schema. If a name was reused, the newest row
    decides — an old archived namesake must not report the live one as gone."""
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tasks (id, project_id, name, status, archived_at, created_at) "
        "VALUES ('old', 'proj-1', 'dup-name', 'in_progress', '2026-07-14T00:00:00Z', '2026-07-14T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO tasks (id, project_id, name, status, archived_at, created_at) "
        "VALUES ('new', 'proj-1', 'dup-name', 'in_progress', NULL, '2026-07-15T00:00:00Z')"
    )
    conn.commit()
    conn.close()
    assert task_state(db, "dup-name") == "live"
