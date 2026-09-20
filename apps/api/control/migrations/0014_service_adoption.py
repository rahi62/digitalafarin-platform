from django.db import migrations, models


def _binding(row):
    return row.target_server_id, f"{row.project.slug}-{row.name}.service"


def _assert_unique_bindings(rows):
    seen = set()
    for row in rows:
        key = _binding(row)
        if key in seen:
            raise RuntimeError("duplicate service unit binding")
        seen.add(key)


def backfill_existing_services(apps, schema_editor):
    Service = apps.get_model("control", "Service")
    rows = list(Service.objects.select_related("project").order_by("pk"))
    _assert_unique_bindings(rows)
    for row in rows:
        Service.objects.filter(pk=row.pk).update(
            unit_name=f"{row.project.slug}-{row.name}.service",
            lifecycle_state="managed",
        )


class Migration(migrations.Migration):
    dependencies = [("control", "0013_domains")]

    operations = [
        migrations.AddField(
            model_name="service",
            name="unit_name",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="service",
            name="lifecycle_state",
            field=models.CharField(
                choices=[
                    ("adopted", "Adopted"),
                    ("configured", "Configured"),
                    ("managed", "Managed"),
                ],
                default="managed",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="service",
            name="repository",
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
        migrations.AlterField(
            model_name="service",
            name="branch",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="service",
            name="root_directory",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="service",
            name="runtime",
            field=models.CharField(
                blank=True,
                choices=[
                    ("node-nextjs", "Node/Next.js"),
                    ("python-django", "Python/Django"),
                ],
                max_length=32,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="service",
            name="service_port",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_existing_services, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="service",
            name="unit_name",
            field=models.CharField(max_length=255),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.UniqueConstraint(
                fields=("target_server", "unit_name"),
                name="uniq_server_service_unit",
            ),
        ),
    ]
