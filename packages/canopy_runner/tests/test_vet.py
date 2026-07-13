import json
import sqlite3
from pathlib import Path

from canopy_runner.emdash import table_fingerprint
from canopy_runner.main import vet

TABLES = ["automations", "automation_runs", "tasks"]


def _make_db(path: Path, migration_id: int, extra_col: str = "") -> None:
    conn = sqlite3.connect(path)
    conn.executescript(f"""
        CREATE TABLE __drizzle_migrations (id INTEGER PRIMARY KEY, hash TEXT, created_at INTEGER);
        INSERT INTO __drizzle_migrations (id, hash, created_at) VALUES ({migration_id}, 'h', 0);
        CREATE TABLE automations (id TEXT PRIMARY KEY, name TEXT NOT NULL{extra_col});
        CREATE TABLE automation_runs (id TEXT PRIMARY KEY, automation_id TEXT NOT NULL, status TEXT NOT NULL, trigger_kind TEXT NOT NULL);
        CREATE TABLE tasks (id TEXT PRIMARY KEY, type TEXT DEFAULT 'task' NOT NULL, automation_run_id TEXT);
    """)
    conn.commit(); conn.close()


def _cfg_file(tmp_path: Path, db: Path, migration_id: int, fingerprint: str = "") -> Path:
    cfg = tmp_path / "runner.json"
    cfg.write_text(json.dumps({
        "base_url": "http://x", "token": "t", "runner_id": "r-1",
        "emdash_db": str(db), "automation_ids": {"echo": "a-1"},
        "expected_migration_id": migration_id, "emdash_fingerprint": fingerprint,
    }))
    return cfg


def test_fingerprint_stable_and_order_independent(tmp_path):
    db = tmp_path / "e.db"; _make_db(db, 19)
    f1 = table_fingerprint(str(db), TABLES)
    f2 = table_fingerprint(str(db), list(reversed(TABLES)))
    assert f1 == f2 and len(f1) == 64


def test_vet_bumps_pin_when_schema_unchanged(tmp_path):
    db = tmp_path / "e.db"; _make_db(db, 19)
    fp = table_fingerprint(str(db), TABLES)
    cfg = _cfg_file(tmp_path, db, migration_id=18, fingerprint=fp)  # emdash updated 18->19, schema same
    result = vet(cfg)
    assert result == "vetted:18->19"
    assert json.loads(cfg.read_text())["expected_migration_id"] == 19


def test_vet_refuses_when_schema_changed(tmp_path):
    db = tmp_path / "e.db"; _make_db(db, 19, extra_col=", new_col TEXT")
    old_db = tmp_path / "old.db"; _make_db(old_db, 18)
    old_fp = table_fingerprint(str(old_db), TABLES)
    cfg = _cfg_file(tmp_path, db, migration_id=18, fingerprint=old_fp)
    result = vet(cfg)
    assert result == "refused"
    assert json.loads(cfg.read_text())["expected_migration_id"] == 18  # untouched


def test_vet_unchanged_when_pin_current(tmp_path):
    db = tmp_path / "e.db"; _make_db(db, 19)
    fp = table_fingerprint(str(db), TABLES)
    cfg = _cfg_file(tmp_path, db, migration_id=19, fingerprint=fp)
    assert vet(cfg) == "unchanged"


def test_vet_adopts_fingerprint_on_first_run(tmp_path):
    # No stored fingerprint yet (fresh install): vet records it without bumping semantics
    db = tmp_path / "e.db"; _make_db(db, 19)
    cfg = _cfg_file(tmp_path, db, migration_id=19, fingerprint="")
    assert vet(cfg) == "unchanged"
    assert json.loads(cfg.read_text())["emdash_fingerprint"] != ""
