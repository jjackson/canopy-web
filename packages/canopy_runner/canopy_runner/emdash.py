"""Emdash sqlite adapter — READ-ONLY.

The CDP executor drives emdash's real UI (create/reuse sessions); it never writes
to emdash's DB. But the DOM cannot answer "does this task still exist?" — emdash
virtualizes the sidebar, so a scrolled-out task is absent from the page — so the
reuse decision asks sqlite instead (`task_state`), and the phone's session list is
read the same way (`list_open_sessions`).

Both reads are deliberately **fail-soft**: any sqlite error degrades to "unknown" /
`[]` rather than raising, because a read failure must never be mistaken for "session
gone" (that false negative duplicated a live session — see `task_state`). The cost of
that safety is that a *silent* schema drift — emdash renaming a column these queries
name — would quietly break the runner (duplicate sessions, a blank supervisor) with
nothing in the log. `check_read_schema` (surfaced as `canopy_runner verify-emdash`)
is the one guard against that: run it after an emdash update to confirm the columns
these two functions depend on still exist. Keep `READ_SCHEMA` in lockstep with the
SQL below — it IS the list of columns the SQL names.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# The exact columns the two reads below depend on. verify-emdash asserts these
# still exist after an emdash update. Update this the moment you change the SQL.
READ_SCHEMA: dict[str, list[str]] = {
    "tasks": [
        "name",
        "archived_at",
        "created_at",
        "status",
        "last_interacted_at",
        "type",
        "project_id",
    ],
    "projects": ["id", "name"],
}


class SchemaCheckError(Exception):
    """The emdash DB itself couldn't be opened/read — distinct from a column drift,
    so 'the DB isn't there' isn't mistaken for 'the schema changed'."""


@contextmanager
def _db(db_path: str) -> Iterator[sqlite3.Connection]:
    """Open a connection and guarantee it is closed.

    ``sqlite3.Connection`` used as a context manager only commits/rolls back the
    transaction on `__exit__` — it does NOT close the connection. Every caller here
    must go through this helper so the underlying file handle is always released.
    """
    conn = sqlite3.connect(db_path, timeout=3.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def check_read_schema(db_path: str) -> list[str]:
    """Verify every column the CDP-path reads depend on still exists.

    Returns a list of human-readable problems (``"tasks.foo missing"``,
    ``"table 'projects' missing"``); an EMPTY list means the read surface is intact.
    Raises ``SchemaCheckError`` if the DB itself can't be opened, so "can't find the
    DB" stays distinct from "the schema drifted".
    """
    if not Path(db_path).exists():  # don't let sqlite3.connect() create an empty file
        raise SchemaCheckError(f"emdash DB not found at {db_path}")
    problems: list[str] = []
    try:
        with _db(db_path) as conn:
            for table, cols in READ_SCHEMA.items():
                # PRAGMA can't be parameter-bound; the table name is our own constant,
                # never user input, so the f-string is safe here.
                present = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                if not present:
                    problems.append(f"table {table!r} missing (or has no columns)")
                    continue
                problems.extend(f"{table}.{col} missing" for col in cols if col not in present)
    except sqlite3.Error as exc:
        raise SchemaCheckError(f"cannot read emdash DB {db_path}: {exc}") from exc
    return problems


def task_state(db_path: str, name: str) -> str:
    """READ-ONLY: is the emdash task `name` live, archived, or absent in THIS account's
    emdash? Returns "live" | "archived" | "absent" | "unknown".

    This is the source of truth for the session-reuse decision, because the DOM is not:
    emdash VIRTUALIZES the sidebar, so a task scrolled out of view isn't in the page at
    all — indistinguishable, to a DOM query, from a task that never existed. That false
    negative made the runner spawn a duplicate session and orphan the live one's context
    (observed 2026-07-15: eva's org-research thread, task provably present and
    un-archived, reported TASK_NOT_FOUND). sqlite always knows, in one query.

    "unknown" (missing/unreadable/drifted DB) is deliberately distinct from "absent": a
    read failure must never be mistaken for "gone", or we're back to duplicating live
    sessions. Callers degrade to the CDP verdict on "unknown" — see execute.execute_turn.

    Names aren't unique in emdash's schema, so the newest row wins: an old archived
    namesake must not report a live task as gone.
    """
    if not Path(db_path).exists():          # don't let sqlite3.connect() create one
        return "unknown"
    try:
        with _db(db_path) as conn:
            row = conn.execute(
                "SELECT archived_at FROM tasks WHERE name=? ORDER BY created_at DESC LIMIT 1",
                (name,),
            ).fetchone()
    except sqlite3.Error:
        return "unknown"
    if row is None:
        return "absent"
    return "archived" if row["archived_at"] else "live"


def list_open_sessions(db_path: str, limit: int = 30) -> list[dict]:
    """READ-ONLY: the un-archived emdash tasks, newest-first, capped. Returns
    [{emdash_task, project, status, last_interacted_at}]. Like task_state this is a
    pure read that must NEVER raise: a missing DB, a renamed column, or an emdash schema
    change degrades to [] so the runner loop survives. The task NAME is the identity
    open_and_send targets; project is joined from `projects` for display + the continue
    turn's target.

    Only `type='task'` rows — the real sessions emdash shows in its project list.
    `type='automation-run'` rows are un-promoted automation triggers that emdash hides
    under "Automations", not sessions a human opened; including them leaked phantom rows
    into the supervisor (e.g. an 8-day-old `plain-keys-rescue`) that don't appear in the
    emdash UI. `status` is always 'in_progress' in practice (emdash never updates it), so
    the display leans on last_interacted_at instead."""
    if not Path(db_path).exists():
        return []
    try:
        with _db(db_path) as conn:
            rows = conn.execute(
                """
                SELECT t.name AS emdash_task,
                       COALESCE(p.name, '') AS project,
                       COALESCE(t.status, '') AS status,
                       t.last_interacted_at AS last_interacted_at
                FROM tasks t
                LEFT JOIN projects p ON p.id = t.project_id
                WHERE t.archived_at IS NULL AND t.type = 'task'
                ORDER BY t.last_interacted_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
