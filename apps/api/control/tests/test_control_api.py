from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import (
    Server,
    ServiceCredential,
    ServicePrincipal,
    ServiceSnapshot,
)
from control.security import issue_secret


class ControlAPITests(TestCase):
    def setUp(self):
        self.server = Server.objects.create(
            name="Primary",
            hostname="primary",
            is_default=True,
        )
        ServiceSnapshot.objects.create(
            server=self.server,
            unit_name="digitalafarin-platform-api.service",
            description="API",
            load_state="loaded",
            active_state="active",
            sub_state="running",
        )
        principal = ServicePrincipal.objects.create(
            name="chatgpt-vps-mcp",
            scopes=["servers:read", "metrics:read", "services:read", "audit:read"],
        )
        issued = issue_secret("service")
        ServiceCredential.objects.create(
            principal=principal,
            token_prefix=issued.prefix,
            token_hash=issued.digest,
        )
        self.token = issued.cleartext
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def test_default_server_uses_uuid_external_id(self):
        response = self.client.get("/api/control/v1/servers/default/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.server.public_id))
        self.assertNotIn("agent_url", response.json())

    def test_service_list_is_server_scoped(self):
        response = self.client.get("/api/control/v1/servers/default/services/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["items"][0]["unit_name"],
            "digitalafarin-platform-api.service",
        )

    def test_metrics_unavailable_before_first_heartbeat(self):
        response = self.client.get("/api/control/v1/servers/default/metrics/")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "metrics_unavailable")

    def test_offline_metrics_are_rejected(self):
        self.server.last_seen_at = timezone.now() - timedelta(seconds=121)
        self.server.save(update_fields=["last_seen_at"])

        response = self.client.get("/api/control/v1/servers/default/metrics/")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "server_offline")

    def test_missing_scope_is_forbidden(self):
        principal = ServicePrincipal.objects.get(name="chatgpt-vps-mcp")
        principal.scopes = ["servers:read"]
        principal.save(update_fields=["scopes"])

        response = self.client.get("/api/control/v1/servers/default/metrics/")

        self.assertEqual(response.status_code, 403)
