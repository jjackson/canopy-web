"""One-time backfill so scoping runner claims to a workspace is non-breaking.

Migration 0004_runner_workspace added the column as NULL, so every existing
runner is untenanted while apps/agents/migrations/0007_backfill_default_
workspace.py already homed every existing agent to the 'dimagi' workspace.
Without this backfill, claim_next_turn's new tenant predicate (null runner ->
null-workspace agents only) would make the live untenanted runner claim
nothing, silently stopping the fleet.

Mirrors apps/agents/migrations/0007_backfill_default_workspace.py: forward-only
(reverse is a no-op — data stays), no-ops cleanly on a fresh DB, and does NOT
create the 'dimagi' workspace here (0007 already does that) — this migration
only looks it up by slug and no-ops if it doesn't exist yet.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    Workspace = apps.get_model("workspaces", "Workspace")
    Runner = apps.get_model("harness", "Runner")

    ws = Workspace.objects.filter(slug="dimagi").first()
    if ws is None:
        return  # 0007 hasn't run (or there were no users) — nothing to home to

    untenanted = Runner.objects.filter(workspace__isnull=True)
    for runner in untenanted.iterator():
        # Prefer homing to paired_by's workspace where that's unambiguous (their
        # sole membership); otherwise fall back to the 'dimagi' default.
        target = ws
        if runner.paired_by_id:
            memberships = list(
                Workspace.objects.filter(memberships__user_id=runner.paired_by_id)[:2]
            )
            if len(memberships) == 1:
                target = memberships[0]
        runner.workspace = target
        runner.save(update_fields=["workspace"])


class Migration(migrations.Migration):
    dependencies = [
        ("harness", "0004_runner_workspace"),
        ("agents", "0007_backfill_default_workspace"),
    ]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
