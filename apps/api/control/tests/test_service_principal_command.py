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
            ],
        )
        self.assertTrue(output.getvalue().startswith("da_service_"))
