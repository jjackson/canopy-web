from django.db import migrations


class Migration(migrations.Migration):
    """Rename Walkthrough.feature → narrative_slug.

    `feature` was a misnomer — it is the narrative's identity (the slug runs
    group under), already exposed externally as `narrative_slug`/`slug`. This
    RenameField preserves all existing data (it renames the column in place).
    """

    dependencies = [
        ("walkthroughs", "0004_walkthrough_narrative_review_id"),
    ]

    operations = [
        migrations.RenameField(
            model_name="walkthrough",
            old_name="feature",
            new_name="narrative_slug",
        ),
    ]
