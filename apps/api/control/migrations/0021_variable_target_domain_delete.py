from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("control", "0020_domain_external_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="environmentvariable",
            name="target",
            field=models.CharField(
                choices=[
                    ("build", "Build"),
                    ("runtime", "Runtime"),
                    ("both", "Build and runtime"),
                ],
                default="both",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="operation",
            name="kind",
            field=models.CharField(
                choices=[
                    ("service.start", "Start service"),
                    ("service.stop", "Stop service"),
                    ("service.restart", "Restart service"),
                    ("service.logs", "Read service logs"),
                    ("service.delete", "Delete managed service"),
                    ("volume.create", "Create managed volume"),
                    ("server.bootstrap", "Bootstrap server"),
                    ("database.create", "Create database"),
                    ("database.restore", "Restore database"),
                    ("deployment.deploy", "Deploy release"),
                    ("deployment.rollback", "Rollback release"),
                    ("domain.configure", "Configure domain"),
                    ("domain.ssl", "Enable domain SSL"),
                    ("domain.delete", "Delete domain"),
                    ("service.takeover.prepare", "Prepare controlled service takeover"),
                    ("service.takeover.activate", "Activate controlled service takeover"),
                ],
                max_length=64,
            ),
        ),
    ]
