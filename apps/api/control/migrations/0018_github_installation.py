from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("control", "0017_operation_service_delete")]

    operations = [
        migrations.CreateModel(
            name="GitHubInstallation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("installation_id", models.PositiveBigIntegerField(unique=True)),
                ("account_login", models.CharField(max_length=255)),
                ("account_type", models.CharField(blank=True, max_length=32)),
                ("repository_selection", models.CharField(blank=True, max_length=32)),
                ("suspended", models.BooleanField(default=False)),
                ("installed_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["account_login"]},
        ),
    ]
