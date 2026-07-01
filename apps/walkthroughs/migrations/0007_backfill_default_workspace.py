"""One-time backfill so scoping walkthroughs to a workspace is non-breaking.

Ensures the default workspace exists (creating it + making every existing user a
member if the agents backfill hasn't already run — get_or_create is idempotent),
then assigns every existing walkthrough to it. Forward-only; the reverse is a
no-op (data stays). On a fresh DB (no users) this no-ops — there is nothing to
scope, and public (visibility=link) reads never depend on the workspace anyway.
"""
from django.conf import settings
from django.db import migrations


def backfill(apps, schema_editor):
    Workspace = apps.get_model("workspaces", "Workspace")
    Membership = apps.get_model("workspaces", "WorkspaceMembership")
    Walkthrough = apps.get_model("walkthroughs", "Walkthrough")
    user_app, user_model = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app, user_model)

    owner = (
        User.objects.filter(is_superuser=True).order_by("id").first()
        or User.objects.order_by("id").first()
    )
    if owner is None:
        return  # fresh DB — no users, no walkthroughs to scope

    raw = getattr(settings, "AUTH_ALLOWED_EMAIL_DOMAIN", "") or ""
    domains = [d.strip().lower() for d in raw.split(",") if d.strip()]

    ws, _ = Workspace.objects.get_or_create(
        slug="dimagi",
        defaults={
            "display_name": "Dimagi",
            "created_by": owner,
            "auto_join_domains": domains,
        },
    )
    for u in User.objects.all().iterator():
        Membership.objects.get_or_create(
            workspace=ws,
            user=u,
            defaults={"role": "owner" if u.pk == owner.pk else "editor"},
        )
    Walkthrough.objects.filter(workspace__isnull=True).update(workspace=ws)


class Migration(migrations.Migration):
    dependencies = [
        ("walkthroughs", "0006_walkthrough_workspace"),
        ("workspaces", "0001_initial"),
    ]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
