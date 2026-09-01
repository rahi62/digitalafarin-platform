# Generated manually for the initial MVP schema.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=100)),
                ("target_type", models.CharField(blank=True, max_length=100)),
                ("target_id", models.CharField(blank=True, max_length=100)),
                ("actor", models.CharField(default="system", max_length=120)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Server",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("hostname", models.CharField(blank=True, max_length=255)),
                ("agent_url", models.URLField(default="http://127.0.0.1:9743")),
                ("is_active", models.BooleanField(default=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("cpu_percent", models.FloatField(default=0)),
                ("memory_percent", models.FloatField(default=0)),
                ("disk_percent", models.FloatField(default=0)),
                ("uptime_seconds", models.BigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ServiceSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("unit_name", models.CharField(max_length=255)),
                ("description", models.CharField(blank=True, max_length=500)),
                ("load_state", models.CharField(max_length=32)),
                ("active_state", models.CharField(max_length=32)),
                ("sub_state", models.CharField(max_length=32)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("server", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="services", to="control.server")),
            ],
            options={"ordering": ["unit_name"]},
        ),
        migrations.AddConstraint(
            model_name="servicesnapshot",
            constraint=models.UniqueConstraint(fields=("server", "unit_name"), name="uniq_server_unit"),
        ),
    ]
