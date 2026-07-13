"""Emdash adapter: trigger a visible emdash session by inserting a queued
automation run. Unsupported-surface rules:

- NEVER write when the Drizzle migration id differs from the vetted pin.
- Only two writes exist: INSERT into automation_runs, UPDATE tasks.type.
- Everything else (task creation, worktree, session spawn) is emdash's own
  runtime reacting to the queued row — verified by live experiment 2026-07-05.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator

VETTED_TABLES = ["automations", "automation_runs", "tasks"]


class SchemaDrift(Exception):
    """emdash migrated its DB; injection is disabled until re-vetted."""


@contextmanager
def _db(db_path: str) -> Iterator[sqlite3.Connection]:
    """Open a connection and guarantee it is closed.

    ``sqlite3.Connection`` used as a context manager only commits/rolls back
    the transaction on `__exit__` — it does NOT close the connection. Every
    caller here must go through this helper (instead of holding a bare
    connection open) so the underlying file handle is always released, on
    both the read and write paths.
    """
    conn = sqlite3.connect(db_path, timeout=3.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _table_sqls(db_path: str, tables: list[str]) -> dict[str, str]:
    """Normalized CREATE TABLE SQL per named table (missing tables absent)."""
    with _db(db_path) as conn:
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN (%s)"
            % ",".join("?" * len(tables)),
            list(tables),
        ).fetchall()
    return {r["name"]: " ".join((r["sql"] or "").split()) for r in rows}


def table_fingerprint(db_path: str, tables: list[str]) -> str:
    """sha256 over the normalized CREATE TABLE SQL of the named tables.

    The migration id moves on every emdash release; the shape of the three
    tables we touch almost never does. Fingerprint-match => safe to re-pin.
    """
    sqls = _table_sqls(db_path, tables)
    parts = [f"{name}::{sql}" for name, sql in sqls.items()]
    return hashlib.sha256("\n".join(sorted(parts)).encode()).hexdigest()


def per_table_fingerprints(db_path: str, tables: list[str]) -> dict[str, str]:
    """sha256 per table over its normalized CREATE TABLE SQL.

    Stored alongside the combined fingerprint so a refusal can name exactly
    which tables changed instead of just "something drifted".
    """
    sqls = _table_sqls(db_path, tables)
    return {name: hashlib.sha256(sql.encode()).hexdigest() for name, sql in sqls.items()}


def check_schema(db_path: str, expected_migration_id: int) -> None:
    with _db(db_path) as conn:
        try:
            row = conn.execute("SELECT MAX(id) AS m FROM __drizzle_migrations").fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                raise SchemaDrift(f"no __drizzle_migrations table in {db_path}") from exc
            raise
    actual = row["m"] if row else None
    if actual != expected_migration_id:
        raise SchemaDrift(
            f"emdash migration id {actual} != vetted {expected_migration_id}; refusing to write"
        )


def inject_run(db_path: str, automation_id: str, run_id: str, task_name: str) -> None:
    """Insert a queued automation_runs row to trigger a visible emdash session.

    Idempotent on ``run_id``: the runner generates ``run_id`` itself, so a
    duplicate call (e.g. a retry after an ambiguous crash where the caller
    couldn't tell whether the prior INSERT committed) means "same intended
    injection" — the row is left untouched and this returns without raising.
    """
    now_ms = int(time.time() * 1000)
    with _db(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM automation_runs WHERE id=?", (run_id,)
        ).fetchone()
        if existing is not None:
            return
        auto = conn.execute(
            "SELECT id, task_config, conversation_config, enabled, deleted_at FROM automations WHERE id=?",
            (automation_id,),
        ).fetchone()
        if auto is None or auto["deleted_at"] is not None:
            raise ValueError(f"automation {automation_id} not found in {db_path}")
        if not auto["enabled"]:
            raise ValueError(f"automation {automation_id} is disabled")
        conn.execute(
            "INSERT INTO automation_runs (id, automation_id, scheduled_at, deadline_at, started_at,"
            " task_created_at, launched_at, finished_at, status, error, trigger_kind,"
            " trigger_config_snapshot, conversation_config_snapshot, task_config_snapshot, generated_task_name)"
            " VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, 'queued', NULL, 'manual', '{}', ?, ?, ?)",
            (
                run_id,
                automation_id,
                now_ms,
                auto["conversation_config"] or "{}",
                auto["task_config"],
                task_name,
            ),
        )
        conn.commit()


def run_status(db_path: str, run_id: str) -> str | None:
    with _db(db_path) as conn:
        row = conn.execute("SELECT status FROM automation_runs WHERE id=?", (run_id,)).fetchone()
    return row["status"] if row else None


def find_task(db_path: str, automation_run_id: str) -> dict | None:
    with _db(db_path) as conn:
        row = conn.execute(
            "SELECT id, name, status, type FROM tasks WHERE automation_run_id=?",
            (automation_run_id,),
        ).fetchone()
    return dict(row) if row else None


def promote_task(db_path: str, task_id: str) -> None:
    with _db(db_path) as conn:
        conn.execute(
            "UPDATE tasks SET type='task', updated_at=datetime('now') WHERE id=?", (task_id,)
        )
        conn.commit()
