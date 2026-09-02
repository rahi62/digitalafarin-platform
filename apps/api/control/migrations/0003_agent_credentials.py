from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("control", "0002_multiserver_identity")]

    operations = [
        migrations.CreateModel(
            name="EnrollmentToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_prefix", models.CharField(max_length=32, unique=True)),
                ("secret_hash", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.CharField(max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="AgentCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_prefix", models.CharField(max_length=32, unique=True)),
                ("token_hash", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("server", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agent_credentials", to="control.server")),
            ],
        ),
    ]
