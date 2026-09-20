import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("control", "0014_service_adoption")]

    operations = [
        migrations.AlterField(
            model_name="operation",
            name="kind",
            field=models.CharField(
                choices=[
                    ("service.start", "Start service"),
                    ("service.stop", "Stop service"),
                    ("service.restart", "Restart service"),
                    ("service.logs", "Read service logs"),
                    ("volume.create", "Create managed volume"),
                    ("server.bootstrap", "Bootstrap server"),
                    ("database.create", "Create database"),
                    ("database.restore", "Restore database"),
                    ("deployment.deploy", "Deploy release"),
                    ("deployment.rollback", "Rollback release"),
                    ("domain.configure", "Configure domain"),
                    ("domain.ssl", "Enable domain SSL"),
                    ("service.takeover.prepare", "Prepare controlled service takeover"),
                    ("service.takeover.activate", "Activate controlled service takeover"),
                ],
                max_length=64,
            ),
        ),
        migrations.CreateModel(
            name="ServiceTakeover",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "public_id",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("inspecting", "Inspecting"),
                            ("preparing", "Preparing"),
                            ("prepared", "Prepared"),
                            ("activating", "Activating"),
                            ("verifying", "Verifying"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("rolled_back", "Rolled back"),
                            ("rollback_failed", "Rollback failed"),
                            ("canceled", "Canceled"),
                        ],
                        default="queued",
                        max_length=24,
                    ),
                ),
                ("requested_commit", models.CharField(max_length=40)),
                ("resolved_commit", models.CharField(blank=True, max_length=40)),
                ("requested_by", models.CharField(max_length=120)),
                ("source_snapshot", models.JSONField(blank=True, default=dict)),
                ("source_fingerprint", models.CharField(blank=True, max_length=64)),
                ("release_name", models.CharField(blank=True, max_length=80)),
                ("release_path", models.CharField(blank=True, max_length=500)),
                (
                    "previous_current_path",
                    models.CharField(blank=True, max_length=500, null=True),
                ),
                ("managed_dropin_path", models.CharField(blank=True, max_length=500)),
                ("health_check_snapshot", models.JSONField(default=dict)),
                ("failure_code", models.CharField(blank=True, max_length=100)),
                ("failure_message", models.CharField(blank=True, max_length=500)),
                ("queued_at", models.DateTimeField(auto_now_add=True)),
                ("prepared_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "activate_operation",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activated_takeover",
                        to="control.operation",
                    ),
                ),
                (
                    "prepare_operation",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prepared_takeover",
                        to="control.operation",
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="takeovers",
                        to="control.service",
                    ),
                ),
            ],
            options={"ordering": ["-queued_at"]},
        ),
        migrations.AddConstraint(
            model_name="servicetakeover",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("state__in", ("queued", "inspecting", "preparing", "prepared", "activating", "verifying"))
                ),
                fields=("service",),
                name="uniq_active_takeover_per_service",
            ),
        ),
        migrations.AlterField(
            model_name="release",
            name="deployment",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="release",
                to="control.deployment",
            ),
        ),
        migrations.AddField(
            model_name="release",
            name="takeover",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="release",
                to="control.servicetakeover",
            ),
        ),
        migrations.AddConstraint(
            model_name="release",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("deployment__isnull", False), ("takeover__isnull", True))
                    | models.Q(("deployment__isnull", True), ("takeover__isnull", False))
                ),
                name="release_exactly_one_provenance",
            ),
        ),
    ]
