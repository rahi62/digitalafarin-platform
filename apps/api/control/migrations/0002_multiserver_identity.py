# Generated for the additive multi-server identity milestone.
import uuid

from django.db import migrations, models
import django.db.models


class Migration(migrations.Migration):
    dependencies = [("control", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="server",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name="server",
            name="is_default",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="server",
            name="agent_version",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="server",
            name="capabilities",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddConstraint(
            model_name="server",
            constraint=models.UniqueConstraint(
                condition=django.db.models.Q(("is_active", True), ("is_default", True)),
                fields=("is_default",),
                name="uniq_active_default_server",
            ),
        ),
    ]
