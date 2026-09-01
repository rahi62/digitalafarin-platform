from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import AgentCredential, EnrollmentToken, Server
from control.security import issue_secret


class AgentAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        issued = issue_secret("enroll")
        self.enrollment_secret = issued.cleartext
        EnrollmentToken.objects.create(
            token_prefix=issued.prefix,
            secret_hash=issued.digest,
            expires_at=timezone.now() + timedelta(minutes=10),
            created_by="test",
        )

    def enroll(self):
        response = self.client.post(
            "/api/agent/v1/enroll",
            {
                "name": "VPS One",
                "hostname": "vps-one",
                "agent_version": "0.2.0",
                "capabilities": ["metrics", "systemd_inventory"],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.enrollment_secret}",
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_heartbeat_updates_only_authenticated_server(self):
        enrolled = self.enroll()
        other = Server.objects.create(name="Other")
        response = self.client.post(
            "/api/agent/v1/heartbeat",
            {
                "agent_version": "0.2.0",
                "hostname": "vps-one",
                "capabilities": ["metrics", "systemd_inventory"],
                "metrics": {
                    "cpu_percent": 12.5,
                    "memory_percent": 40.0,
                    "disk_percent": 25.0,
                    "uptime_seconds": 100,
                },
                "services": [
                    {
                        "unit_name": "digitalafarin-platform-api.service",
                        "description": "API",
                        "load_state": "loaded",
                        "active_state": "active",
                        "sub_state": "running",
                    }
                ],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {enrolled['agent_token']}",
        )

        self.assertEqual(response.status_code, 204)
        server = Server.objects.get(public_id=enrolled["server_id"])
        self.assertEqual(server.cpu_percent, 12.5)
        self.assertEqual(server.services.count(), 1)
        other.refresh_from_db()
        self.assertIsNone(other.last_seen_at)

    def test_revoked_credential_cannot_heartbeat(self):
        enrolled = self.enroll()
        credential = AgentCredential.objects.get(server__public_id=enrolled["server_id"])
        credential.revoked_at = timezone.now()
        credential.save(update_fields=["revoked_at"])
        response = self.client.post(
            "/api/agent/v1/heartbeat",
            {
                "agent_version": "0.2.0",
                "hostname": "vps-one",
                "capabilities": [],
                "metrics": {
                    "cpu_percent": 1,
                    "memory_percent": 1,
                    "disk_percent": 1,
                    "uptime_seconds": 1,
                },
                "services": [],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {enrolled['agent_token']}",
        )

        self.assertEqual(response.status_code, 401)
