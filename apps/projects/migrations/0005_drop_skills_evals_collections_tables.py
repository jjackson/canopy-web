"""Drop the orphaned skill-authoring tables.

The `skills`, `evals`, and `collections` apps were removed (PR #174) — the
build-reusable-skills-from-conversations surface is gone. Their tables were
left behind at that point (harmless, but dead). This migration drops them.

Lives in `projects` (a product app with an active migration chain) purely as a
host; the dropped tables all belonged to now-deleted product apps.

Portability + real-DB dependents: on Postgres we drop with ``CASCADE`` because
the *live* labs DB still carries legacy tables from the long-retired co-authoring
app (`workspace_workspacesession`) whose FK constraints reference
`collections_collection` / `skills_skill`. Those tables don't exist in the SQLite
test DB, so a plain drop passed CI but failed on Postgres. ``CASCADE`` drops only
the dead dependent *constraints* (no retained table references any of these);
SQLite doesn't support ``CASCADE`` (and has no such dependents), so we omit it
there. ``IF EXISTS`` keeps the whole thing a no-op on fresh DBs.

Irreversible: the data is gone. ``reverse`` is a no-op so the migration can be
unapplied in the graph without error (it does not recreate the tables/data).
"""
from __future__ import annotations

from django.db import migrations

# Child tables before their parents; CASCADE (Postgres) also clears any legacy
# external FK constraints still pointing at these dead tables.
_TABLES = [
    "evals_evalrun",
    "evals_evalcase",
    "evals_evalsuite",
    "skills_skill",
    "collections_source",
    "collections_collection",
]


def _drop_tables(apps, schema_editor):
    conn = schema_editor.connection
    cascade = " CASCADE" if conn.vendor == "postgresql" else ""
    with conn.cursor() as cursor:
        for table in _TABLES:
            cursor.execute(f"DROP TABLE IF EXISTS {table}{cascade};")
        # Tidy the migration ledger so nothing dangles for the removed apps.
        cursor.execute(
            "DELETE FROM django_migrations WHERE app IN ('skills', 'evals', 'collections');"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0004_drop_project_guide"),
    ]

    operations = [
        migrations.RunPython(_drop_tables, migrations.RunPython.noop),
    ]
