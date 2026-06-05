from django.db import migrations


class Migration(migrations.Migration):
    """Rename ReviewRequest.feature → narrative_slug.

    `feature` was a misnomer — it is the narrative's identity (the slug runs
    group under), already exposed externally as `narrative_slug`/`slug`. This
    RenameField preserves all existing data (it renames the column in place);
    the composite ``(feature, version)`` index follows the column rename.
    """

    dependencies = [
        ("reviews", "0002_reviewrequest_feature_reviewrequest_version_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="reviewrequest",
            old_name="feature",
            new_name="narrative_slug",
        ),
    ]
