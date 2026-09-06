import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("control", "0004_service_principals"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramBotCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="primary", max_length=120, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("token_ciphertext", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="TelegramChannel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("alias", models.CharField(max_length=80, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("chat_id", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("description", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["alias"]},
        ),
        migrations.CreateModel(
            name="TelegramPublishAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("action", models.CharField(choices=[("test", "Test"), ("publish", "Publish")], max_length=16)),
                ("status", models.CharField(choices=[("success", "Success"), ("failed", "Failed")], max_length=16)),
                ("message_ids", models.JSONField(blank=True, default=list)),
                ("content_preview", models.CharField(blank=True, max_length=280)),
                ("content_sha256", models.CharField(blank=True, max_length=64)),
                ("error_code", models.CharField(blank=True, max_length=100)),
                ("error_message", models.CharField(blank=True, max_length=500)),
                ("actor_principal", models.CharField(default="system", max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("channel", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="publish_audits", to="control.telegramchannel")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
