"""Drop the orphaned skill-authoring tables.

The `skills`, `evals`, and `collections` apps were removed (PR #174) — the
build-reusable-skills-from-conversations surface is gone. Their tables were
left behind at that point (harmless, but dead). This migration drops them.

Lives in `projects` (a product app with an active migration chain) purely as a
host; the dropped tables all belonged to now-deleted product apps. `IF EXISTS`
keeps it a no-op on fresh databases (CI/test SQLite DBs, new deploys) where
these tables were never created.

The SQL is portable across Postgres (production) and SQLite (tests): no
`CASCADE` — tables are dropped child-before-parent so the intra-group FKs
(evals→skills, source→collection) never block a drop, and no retained table
references any of them.

Irreversible: the data is gone. `reverse` is a no-op so the migration can be
unapplied in the graph without error (it does not recreate the tables/data).
"""
from __future__ import annotations

from django.db import migrations

# Child tables before their parents so no FK blocks the drop (no CASCADE needed).
_DROP = [
    "DROP TABLE IF EXISTS evals_evalrun;",
    "DROP TABLE IF EXISTS evals_evalcase;",
    "DROP TABLE IF EXISTS evals_evalsuite;",
    "DROP TABLE IF EXISTS skills_skill;",
    "DROP TABLE IF EXISTS collections_source;",
    "DROP TABLE IF EXISTS collections_collection;",
    # Tidy the migration ledger so nothing dangles for the removed apps.
    "DELETE FROM django_migrations WHERE app IN ('skills', 'evals', 'collections');",
]


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0004_drop_project_guide"),
    ]

    operations = [
        migrations.RunSQL(sql="\n".join(_DROP), reverse_sql=migrations.RunSQL.noop),
    ]
