from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import Project, Server, Service, ServiceCredential, ServicePrincipal, Volume
from control.security import issue_secret


class VolumeAPITests(TestCase):
    def setUp(self):
        self.server = Server.objects.create(name="Target", last_seen_at=timezone.now())
        self.project = Project.objects.create(name="Oily", slug="oily")
        self.service = Service.objects.create(
            project=self.project,
            name="backend",
            repository="https://github.com/example/oily.git",
            branch="main",
            runtime="python-django",
            service_port=8000,
            target_server=self.server,
        )
        principal = ServicePrincipal.objects.create(name="web", scopes=["operations:create", "operations:read"])
        issued = issue_secret("service")
        ServiceCredential.objects.create(principal=principal, token_prefix=issued.prefix, token_hash=issued.digest)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")

    def test_volume_path_is_platform_derived_and_creation_is_queued(self):
        response = self.client.post(
            f"/api/control/v1/projects/{self.project.public_id}/volumes/",
            {
                "name": "media",
                "service_id": str(self.service.public_id),
                "mount_path": "/app/media",
                "owner": "deploy",
                "group": "deploy",
                "mode": "0750",
                "backup_policy": "daily",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["host_path"], "/srv/digitalafarin/volumes/oily/media")
        self.assertEqual(response.json()["operation_state"], "queued")

    def test_volume_rejects_host_path_and_traversal_inputs(self):
        response = self.client.post(
            f"/api/control/v1/projects/{self.project.public_id}/volumes/",
            {
                "name": "../etc",
                "service_id": str(self.service.public_id),
                "host_path": "/etc",
                "mount_path": "../../etc",
                "owner": "root;id",
                "group": "root",
                "mode": "7777",
                "backup_policy": "daily",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Volume.objects.count(), 0)
