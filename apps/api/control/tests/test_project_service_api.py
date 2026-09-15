from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import (
    Deployment,
    DeploymentEvent,
    HealthCheck,
    Project,
    Server,
    Service,
    ServiceCredential,
    ServicePrincipal,
)
from control.security import issue_secret


class ProjectServiceAPITests(TestCase):
    def setUp(self):
        self.server = Server.objects.create(
            name="Migration Target", last_seen_at=timezone.now(), disk_percent=30
        )
        principal = ServicePrincipal.objects.create(
            name="platform-web",
            scopes=["operations:read", "operations:create"],
        )
        issued = issue_secret("service")
        ServiceCredential.objects.create(
            principal=principal,
            token_prefix=issued.prefix,
            token_hash=issued.digest,
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")

    def test_project_and_structured_systemd_service_can_be_created(self):
        project_response = self.client.post(
            "/api/control/v1/projects/",
            {"name": "Oily", "slug": "oily"},
            format="json",
        )
        self.assertEqual(project_response.status_code, 201)

        service_response = self.client.post(
            f"/api/control/v1/projects/{project_response.json()['id']}/services/",
            {
                "name": "backend",
                "executor": "systemd",
                "repository": "https://github.com/example/oily.git",
                "branch": "main",
                "root_directory": "backend",
                "runtime": "python-django",
                "install_configuration": {"requirements_file": "requirements.txt"},
                "build_configuration": {"migrate": True, "collectstatic": True},
                "service_port": 8000,
                "target_server_id": str(self.server.public_id),
            },
            format="json",
        )

        self.assertEqual(service_response.status_code, 201)
        self.assertEqual(service_response.json()["executor"], "systemd")
        self.assertEqual(Service.objects.get().project.slug, "oily")
        self.assertNotIn("credential", str(service_response.json()).lower())

    def test_service_rejects_unknown_executor_and_shell_configuration(self):
        project = Project.objects.create(name="Oily", slug="oily")
        base = {
            "name": "backend",
            "repository": "https://github.com/example/oily.git",
            "branch": "main",
            "root_directory": "backend",
            "runtime": "python-django",
            "install_configuration": {},
            "build_configuration": {},
            "service_port": 8000,
            "target_server_id": str(self.server.public_id),
        }
        unknown = self.client.post(
            f"/api/control/v1/projects/{project.public_id}/services/",
            {**base, "executor": "docker"},
            format="json",
        )
        command = self.client.post(
            f"/api/control/v1/projects/{project.public_id}/services/",
            {
                **base,
                "executor": "systemd",
                "build_configuration": {"command": "rm -rf /"},
            },
            format="json",
        )

        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(command.status_code, 400)
        self.assertEqual(Service.objects.count(), 0)

    def test_health_check_and_deployment_event_have_uuid_identity(self):
        project = Project.objects.create(name="Oily", slug="oily")
        service = Service.objects.create(
            project=project,
            name="web",
            executor="systemd",
            repository="https://github.com/example/oily.git",
            branch="main",
            runtime="node-nextjs",
            service_port=3000,
            target_server=self.server,
        )
        check = HealthCheck.objects.create(service=service, path="/health")
        deployment = Deployment.objects.create(
            service=service, requested_ref="main", requested_by="operator"
        )
        event = DeploymentEvent.objects.create(
            deployment=deployment, state="queued", message="Deployment queued"
        )

        self.assertIsNotNone(check.public_id)
        self.assertIsNotNone(deployment.public_id)
        self.assertIsNotNone(event.public_id)
        self.assertEqual(deployment.state, "queued")
