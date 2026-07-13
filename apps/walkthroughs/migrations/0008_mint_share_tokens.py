"""Mint share tokens for pre-existing public walkthroughs.

The share-token revival (spec 2026-07-13) makes anonymous read require
?t=<share_token>. Rows that were already visibility=link need a token so
their owners can re-share without re-toggling visibility.
"""
import secrets

from django.db import migrations
from django.db.models import Q


def mint_tokens(apps, schema_editor):
    Walkthrough = apps.get_model("walkthroughs", "Walkthrough")
    qs = Walkthrough.objects.filter(visibility="link").filter(
        Q(share_token__isnull=True) | Q(share_token="")
    )
    for w in qs:
        w.share_token = secrets.token_urlsafe(24)
        w.save(update_fields=["share_token"])


class Migration(migrations.Migration):
    dependencies = [
        ("walkthroughs", "0007_backfill_default_workspace"),
    ]

    operations = [
        migrations.RunPython(mint_tokens, migrations.RunPython.noop),
    ]
