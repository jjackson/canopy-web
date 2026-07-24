import sqlite3

import pytest

from canopy_runner import emdash


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE projects (id TEXT, name TEXT, path TEXT);
        CREATE TABLE tasks (id TEXT, project_id TEXT, name TEXT, status TEXT,
                            archived_at TEXT, last_interacted_at TEXT, type TEXT);
        INSERT INTO projects VALUES ('p1','canopy-web','/x/canopy-web');
        INSERT INTO tasks VALUES ('t1','p1','cloud-runner','in_progress',NULL,'2026-07-16T15:52:00','task');
        INSERT INTO tasks VALUES ('t2','p1','ddd','in_progress',NULL,'2026-07-16T12:41:00','task');
        INSERT INTO tasks VALUES ('t3','p1','old','done','2026-07-15T00:00:00','2026-07-15T00:00:00','task');
        -- an un-promoted automation-run: emdash hides it under "Automations", so must NOT show.
        INSERT INTO tasks VALUES ('t4','p1','plain-keys-rescue','in_progress',NULL,'2026-07-13T15:01:00','automation-run');
        """
    )
    conn.commit()
    conn.close()


def test_lists_unarchived_tasks_newest_first(tmp_path):
    db = tmp_path / "emdash4.db"
    _make_db(str(db))
    out = emdash.list_open_sessions(str(db))
    # 'old' archived → excluded; 'plain-keys-rescue' is an automation-run → excluded.
    assert [s["emdash_task"] for s in out] == ["cloud-runner", "ddd"]
    assert out[0]["project"] == "canopy-web"
    assert out[0]["last_interacted_at"] == "2026-07-16T15:52:00"


def test_missing_db_returns_empty_not_raises(tmp_path):
    assert emdash.list_open_sessions(str(tmp_path / "nope.db")) == []


def test_a_broken_schema_raises_rather_than_looking_empty(tmp_path):
    """A read failure must NOT look like "zero open sessions". Returning [] here made
    the runner POST an empty report, which clears every RunnerBinding server-side —
    a schema drift silently blanked the supervisor."""
    db = tmp_path / "bad.db"
    sqlite3.connect(str(db)).execute("CREATE TABLE tasks (id TEXT)")  # missing columns
    with pytest.raises(emdash.EmdashReadError):
        emdash.list_open_sessions(str(db))


def test_missing_db_still_returns_empty(tmp_path):
    """A MISSING file is "no emdash here", not a failure — that stays fail-soft."""
    assert emdash.list_open_sessions(str(tmp_path / "nope.db")) == []
