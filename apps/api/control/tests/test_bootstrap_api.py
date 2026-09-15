from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import Operation, Server, ServiceCredential, ServicePrincipal
from control.security import issue_secret


class BootstrapAPITests(TestCase):
    def setUp(self):
        self.server = Server.objects.create(name="Fresh VPS", last_seen_at=timezone.now())
        principal = ServicePrincipal.objects.create(name="web", scopes=["operations:create", "operations:read"])
        issued = issue_secret("service")
        ServiceCredential.objects.create(principal=principal, token_prefix=issued.prefix, token_hash=issued.digest)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")

    def test_bootstrap_queues_fixed_empty_payload(self):
        response = self.client.post(
            f"/api/control/v1/servers/{self.server.public_id}/bootstrap/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        operation = Operation.objects.get(public_id=response.json()["id"])
        self.assertEqual(operation.kind, "server.bootstrap")
        self.assertEqual(operation.payload, {})

    def test_bootstrap_rejects_caller_commands_packages_and_paths(self):
        response = self.client.post(
            f"/api/control/v1/servers/{self.server.public_id}/bootstrap/",
            {"packages": ["netcat"], "path": "/tmp", "command": "id"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Operation.objects.count(), 0)
