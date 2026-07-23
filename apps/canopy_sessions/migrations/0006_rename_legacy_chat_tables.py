"""Rename the legacy `chat_*` tables to `canopy_sessions_*`.

Companion to the `replaces` markers on 0001-0003. When the app was renamed from
`chat` to `canopy_sessions` (PR #350), the default table names changed from
`chat_<model>` to `canopy_sessions_<model>`, but a DB where the old `chat` app
was already applied (labs) still has the physical `chat_*` tables. `replaces`
repairs the migration *history*; this migration repairs the physical *tables*.

Ordering: this runs BEFORE 0004_session_origin (via `run_before`) so that on an
existing DB the rename happens before 0004 does `ALTER TABLE canopy_sessions_session ADD COLUMN`.

Behavior by backend / DB state (the guard makes it a safe no-op everywhere but labs):
  - Postgres, existing `chat_*` DB (labs): 0001-0003 were satisfied via `replaces`
    (never ran), so the `chat_*` tables are present and get renamed here. Postgres
    foreign keys and id-sequence defaults follow the table rename automatically, so
    harness_turn.chat_session_id keeps pointing at the (renamed) session table.
  - Postgres, fresh DB: 0001-0003 already created the `canopy_sessions_*` tables, so
    no `chat_*` table exists — every rename is skipped.
  - SQLite (tests): the test DB always replays fresh under the new label, so no
    `chat_*` table ever exists — skipped. (This is also why we can't emit raw
    `ALTER TABLE IF EXISTS`: SQLite doesn't support that syntax, so we guard in
    Python and only touch Postgres.)

Idempotent + non-destructive: renames only when the source exists and the target
doesn't; the reverse is a no-op (we don't rename back).
"""
from django.db import migrations


# Legacy default table name -> new default table name. Only the models that
# existed under the `chat` label (Session, Message, Draft, SessionParticipant)
# need renaming; RunnerBinding (0005) is new and is created as canopy_sessions_*.
_RENAMES = [
    ("chat_session", "canopy_sessions_session"),
    ("chat_message", "canopy_sessions_message"),
    ("chat_draft", "canopy_sessions_draft"),
    ("chat_sessionparticipant", "canopy_sessions_sessionparticipant"),
]


def _rename_legacy_tables(apps, schema_editor):
    conn = schema_editor.connection
    # Only a Postgres DB that predates the rename can have `chat_*` tables. Fresh
    # DBs and the SQLite test DB never do — and SQLite has no `ALTER TABLE IF
    # EXISTS`, so we must guard in Python rather than in SQL.
    if conn.vendor != "postgresql":
        return
    with conn.cursor() as cursor:
        existing = set(conn.introspection.table_names(cursor))
        for old, new in _RENAMES:
            if old in existing and new not in existing:
                schema_editor.execute(f'ALTER TABLE "{old}" RENAME TO "{new}"')


class Migration(migrations.Migration):

    dependencies = [
        ("canopy_sessions", "0003_session_project_and_more"),
    ]

    # Insert this into the graph BEFORE 0004 without editing 0004/0005.
    run_before = [
        ("canopy_sessions", "0004_session_origin"),
    ]

    operations = [
        migrations.RunPython(
            _rename_legacy_tables,
            migrations.RunPython.noop,
            # A pure table rename carries no ORM state change; keeping it elidable
            # lets a future squash drop it once no `chat_*` DB remains.
            elidable=True,
        ),
    ]
