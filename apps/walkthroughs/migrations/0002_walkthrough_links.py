from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("walkthroughs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="walkthrough",
            name="links",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
