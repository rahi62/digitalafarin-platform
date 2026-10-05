from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("control", "0019_legacy_branch_defaults")]

    operations = [
        migrations.AlterField(
            model_name="domain",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("configured", "Configured"),
                    ("failed", "Failed"),
                    ("external", "External"),
                ],
                default="queued",
                max_length=16,
            ),
        ),
    ]
