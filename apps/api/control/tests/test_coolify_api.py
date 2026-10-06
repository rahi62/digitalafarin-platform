from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from control.models import ServiceCredential, ServicePrincipal
from control.security import issue_secret


class FakeCoolifyClient:
    def version(self):
        return "4.3.23"

    def list_servers(self):
        return [{"uuid": "server-1", "name": "localhost"}]

    def list_projects(self):
        return [{"uuid": "project-1", "name": "PoC"}]

    def list_resources(self):
        return [{"uuid": "resource-1", "name": "demo", "type": "application"}]

    def close(self):
        pass


class CoolifyControlAPITests(TestCase):
    def setUp(self):
        principal = ServicePrincipal.objects.create(
            name="chatgpt-coolify-read",
            scopes=["coolify:read"],
        )
        issued = issue_secret("service")
        ServiceCredential.objects.create(
            principal=principal,
            token_prefix=issued.prefix,
            token_hash=issued.digest,
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")

    @patch("control.coolify_views.CoolifyClient", return_value=FakeCoolifyClient())
    def test_status_is_read_only_and_secret_free(self, _client):
        response = self.client.get("/api/control/v1/coolify/status/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"version": "4.3.23"})

    @patch("control.coolify_views.CoolifyClient", return_value=FakeCoolifyClient())
    def test_inventory_endpoints_wrap_items(self, _client):
        servers = self.client.get("/api/control/v1/coolify/servers/")
        projects = self.client.get("/api/control/v1/coolify/projects/")
        resources = self.client.get("/api/control/v1/coolify/resources/")

        self.assertEqual(servers.status_code, 200)
        self.assertEqual(servers.json()["items"][0]["name"], "localhost")
        self.assertEqual(projects.json()["items"][0]["name"], "PoC")
        self.assertEqual(resources.json()["items"][0]["type"], "application")

    @patch("control.coolify_views.CoolifyClient", return_value=FakeCoolifyClient())
    def test_missing_coolify_scope_is_forbidden(self, _client):
        principal = ServicePrincipal.objects.get(name="chatgpt-coolify-read")
        principal.scopes = ["servers:read"]
        principal.save(update_fields=["scopes"])

        response = self.client.get("/api/control/v1/coolify/status/")

        self.assertEqual(response.status_code, 403)
