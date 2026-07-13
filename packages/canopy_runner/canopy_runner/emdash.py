"""Emdash adapter: trigger a visible emdash session by inserting a queued
automation run. Unsupported-surface rules:

- NEVER write when the Drizzle migration id differs from the vetted pin.
- Only two writes exist: INSERT into automation_runs, UPDATE tasks.type.
- Everything else (task creation, worktree, session spawn) is emdash's own
  runtime reacting to the queued row — verified by live experiment 2026-07-05.
"""
from __future__ import annotations

import json
import sqlite3
import time


class SchemaDrift(Exception):
    """emdash migrated its DB; injection is disabled until re-vetted."""


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=3.0)
    conn.row_factory = sqlite3.Row
    return conn


def check_schema(db_path: str, expected_migration_id: int) -> None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT MAX(id) AS m FROM __drizzle_migrations").fetchone()
    actual = row["m"] if row else None
    if actual != expected_migration_id:
        raise SchemaDrift(
            f"emdash migration id {actual} != vetted {expected_migration_id}; refusing to write"
        )


def inject_run(db_path: str, automation_id: str, run_id: str, task_name: str) -> None:
    now_ms = int(time.time() * 1000)
    with _connect(db_path) as conn:
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
    with _connect(db_path) as conn:
        row = conn.execute("SELECT status FROM automation_runs WHERE id=?", (run_id,)).fetchone()
    return row["status"] if row else None


def find_task(db_path: str, automation_run_id: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, name, status, type FROM tasks WHERE automation_run_id=?",
            (automation_run_id,),
        ).fetchone()
    return dict(row) if row else None


def promote_task(db_path: str, task_id: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE tasks SET type='task', updated_at=datetime('now') WHERE id=?", (task_id,)
        )
        conn.commit()
