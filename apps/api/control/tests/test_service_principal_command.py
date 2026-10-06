from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from control.models import ServicePrincipal


class ServicePrincipalCommandTests(TestCase):
    def test_operator_profile_grants_inventory_and_typed_operation_scopes(self):
        output = StringIO()

        call_command(
            "create_service_principal",
            "migration-operator",
            "--profile",
            "operator",
            stdout=output,
        )

        principal = ServicePrincipal.objects.get(name="migration-operator")
        self.assertEqual(
            principal.scopes,
            [
                "servers:read",
                "metrics:read",
                "services:read",
                "audit:read",
                "operations:read",
                "operations:create",
                "logs:read",
                "coolify:read",
            ],
        )
        self.assertTrue(output.getvalue().startswith("da_service_"))


    def test_upgrade_command_grants_scope_without_rotating_credential(self):
        output = StringIO()
        call_command(
            "create_service_principal",
            "existing-operator",
            "--profile",
            "operator",
            stdout=output,
        )
        principal = ServicePrincipal.objects.get(name="existing-operator")
        principal.scopes = [scope for scope in principal.scopes if scope != "coolify:read"]
        principal.save(update_fields=["scopes"])
        credential_ids = list(principal.credentials.values_list("id", flat=True))

        upgrade_output = StringIO()
        call_command("grant_coolify_read_scope", "--name", "existing-operator", stdout=upgrade_output)

        principal.refresh_from_db()
        self.assertIn("coolify:read", principal.scopes)
        self.assertEqual(
            list(principal.credentials.values_list("id", flat=True)),
            credential_ids,
        )
        self.assertIn("updated=1", upgrade_output.getvalue())
