from django.db import migrations


def set_legacy_defaults(apps, schema_editor):
    """Keep writes compatible with optional columns from the old provisioning branch."""
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        operation_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, "control_operation")
        }
        service_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, "control_service")
        }

    if "progress" in operation_columns:
        schema_editor.execute(
            "ALTER TABLE control_operation ALTER COLUMN progress SET DEFAULT '{}'::jsonb"
        )
    if "progress_sequence" in operation_columns:
        schema_editor.execute(
            "ALTER TABLE control_operation ALTER COLUMN progress_sequence SET DEFAULT 0"
        )
    if "platform_managed" in service_columns:
        schema_editor.execute(
            "ALTER TABLE control_service ALTER COLUMN platform_managed SET DEFAULT false"
        )


class Migration(migrations.Migration):
    dependencies = [("control", "0018_github_installation")]

    operations = [migrations.RunPython(set_legacy_defaults, reverse_code=migrations.RunPython.noop)]
