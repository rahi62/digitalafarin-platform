from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import (
    Deployment,
    AuditEvent,
    DeploymentEvent,
    HealthCheck,
    Operation,
    Project,
    Server,
    Service,
    ServiceCredential,
    ServiceSnapshot,
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
        self.assertEqual(service_response.json()["unit_name"], "oily-backend.service")
        self.assertEqual(service_response.json()["lifecycle_state"], "pending")
        service = Service.objects.get()
        self.assertEqual(service.project.slug, "oily")
        self.assertEqual(service.unit_name, "oily-backend.service")
        self.assertEqual(service.lifecycle_state, 'pending')
        self.assertNotIn("credential", str(service_response.json()).lower())


    def test_project_creation_validates_unique_slug_and_writes_audit_event(self):
        first = self.client.post(
            "/api/control/v1/projects/",
            {"name": "Oily", "slug": "oily"},
            format="json",
        )
        duplicate = self.client.post(
            "/api/control/v1/projects/",
            {"name": "Oily Again", "slug": "oily"},
            format="json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 400)
        event = AuditEvent.objects.get(event_type="project.created")
        self.assertEqual(event.target_id, first.json()["id"])
        self.assertEqual(event.metadata, {"slug": "oily"})

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

    def test_service_representation_marks_missing_inventory_without_deleting_service(self):
        project = Project.objects.create(name="Oily", slug="oily")
        service = Service.objects.create(
            project=project,
            name="backend",
            unit_name="oily-backend.service",
            lifecycle_state=Service.LIFECYCLE_ADOPTED,
            target_server=self.server,
        )

        response = self.client.get(f"/api/control/v1/projects/{project.public_id}/")

        self.assertEqual(response.status_code, 200)
        item = next(
            row for row in response.json()["services"]
            if row["id"] == str(service.public_id)
        )
        self.assertEqual(item["inventory_status"], "missing")
        self.assertIsNone(item["active_state"])
        self.assertFalse(item["protected"])
        self.assertTrue(Service.objects.filter(pk=service.pk).exists())

    def test_service_representation_uses_live_inventory_and_protected_policy(self):
        project = Project.objects.create(name="Platform", slug="platform")
        ServiceSnapshot.objects.create(
            server=self.server,
            unit_name="digitalafarin-platform-web.service",
            description="Platform Web",
            load_state="loaded",
            active_state="active",
            sub_state="running",
        )
        service = Service.objects.create(
            project=project,
            name="web",
            unit_name="digitalafarin-platform-web.service",
            lifecycle_state=Service.LIFECYCLE_ADOPTED,
            target_server=self.server,
        )

        response = self.client.get(f"/api/control/v1/projects/{project.public_id}/")

        self.assertEqual(response.status_code, 200)
        item = next(
            row for row in response.json()["services"]
            if row["id"] == str(service.public_id)
        )
        self.assertEqual(item["inventory_status"], "present")
        self.assertEqual(item["active_state"], "active")
        self.assertEqual(item["sub_state"], "running")
        self.assertTrue(item["protected"])

    def test_adopt_real_inventory_unit_is_metadata_only_and_audited(self):
        project = Project.objects.create(name="Oily", slug="oily")
        ServiceSnapshot.objects.create(
            server=self.server,
            unit_name="oily-backend.service",
            description="Oily backend",
            load_state="loaded",
            active_state="active",
            sub_state="running",
        )
        before_operations = Operation.objects.count()

        response = self.client.post(
            f"/api/control/v1/projects/{project.public_id}/services/adopt/",
            {
                "server_id": str(self.server.public_id),
                "unit_name": "oily-backend.service",
                "name": "backend",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        service = Service.objects.get(public_id=response.json()["id"])
        self.assertEqual(service.lifecycle_state, Service.LIFECYCLE_ADOPTED)
        self.assertEqual(service.unit_name, "oily-backend.service")
        self.assertIsNone(service.repository)
        self.assertEqual(Operation.objects.count(), before_operations)
        event = AuditEvent.objects.get(
            event_type="service.adopted",
            target_id=str(service.public_id),
        )
        self.assertEqual(
            event.metadata,
            {
                "project_id": str(project.public_id),
                "server_id": str(self.server.public_id),
                "unit_name": "oily-backend.service",
                "service_name": "backend",
            },
        )

    def test_adopt_rejects_missing_inventory_duplicate_unit_and_duplicate_project_name(self):
        project = Project.objects.create(name="Oily", slug="oily")
        missing = self.client.post(
            f"/api/control/v1/projects/{project.public_id}/services/adopt/",
            {
                "server_id": str(self.server.public_id),
                "unit_name": "missing.service",
                "name": "missing",
            },
            format="json",
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"], "inventory_unit_not_found")

        ServiceSnapshot.objects.create(
            server=self.server,
            unit_name="oily-backend.service",
            description="Oily backend",
            load_state="loaded",
            active_state="active",
            sub_state="running",
        )
        Service.objects.create(
            project=project,
            name="backend",
            unit_name="oily-backend.service",
            lifecycle_state=Service.LIFECYCLE_ADOPTED,
            target_server=self.server,
        )
        duplicate_unit = self.client.post(
            f"/api/control/v1/projects/{project.public_id}/services/adopt/",
            {
                "server_id": str(self.server.public_id),
                "unit_name": "oily-backend.service",
                "name": "backend-two",
            },
            format="json",
        )
        self.assertEqual(duplicate_unit.status_code, 409)
        self.assertEqual(duplicate_unit.json()["error"], "unit_already_adopted")

        ServiceSnapshot.objects.create(
            server=self.server,
            unit_name="oily-worker.service",
            description="Oily worker",
            load_state="loaded",
            active_state="active",
            sub_state="running",
        )
        duplicate_name = self.client.post(
            f"/api/control/v1/projects/{project.public_id}/services/adopt/",
            {
                "server_id": str(self.server.public_id),
                "unit_name": "oily-worker.service",
                "name": "backend",
            },
            format="json",
        )
        self.assertEqual(duplicate_name.status_code, 409)
        self.assertEqual(duplicate_name.json()["error"], "service_name_in_use")

    def test_configure_adopted_service_moves_to_configured_without_operation(self):
        project = Project.objects.create(name="Oily", slug="oily")
        service = Service.objects.create(
            project=project,
            name="backend",
            unit_name="oily-backend.service",
            lifecycle_state=Service.LIFECYCLE_ADOPTED,
            target_server=self.server,
        )
        before_operations = Operation.objects.count()
        payload = {
            "repository": "https://github.com/example/oily.git",
            "branch": "main",
            "root_directory": "backend",
            "runtime": "python-django",
            "install_configuration": {"requirements_file": "requirements.txt"},
            "build_configuration": {
                "migrate": True,
                "collectstatic": True,
                "gunicorn_module": "config.wsgi:application",
            },
            "service_port": 8000,
        }

        response = self.client.put(
            f"/api/control/v1/services/{service.public_id}/deployment-configuration/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        service.refresh_from_db()
        self.assertEqual(service.lifecycle_state, Service.LIFECYCLE_CONFIGURED)
        self.assertEqual(service.repository, "https://github.com/example/oily.git")
        self.assertEqual(Operation.objects.count(), before_operations)

        second = self.client.put(
            f"/api/control/v1/services/{service.public_id}/deployment-configuration/",
            payload,
            format="json",
        )
        self.assertEqual(second.status_code, 200)
        service.refresh_from_db()
        self.assertEqual(service.lifecycle_state, Service.LIFECYCLE_CONFIGURED)
        event = AuditEvent.objects.filter(
            event_type="service.deployment_configured",
            target_id=str(service.public_id),
        ).latest("created_at")
        self.assertEqual(
            event.metadata["fields"],
            [
                "repository",
                "branch",
                "root_directory",
                "runtime",
                "install_configuration",
                "build_configuration",
                "service_port",
            ],
        )
        self.assertNotIn("github.com", str(event.metadata))
        self.assertNotIn("requirements.txt", str(event.metadata))

    def test_configuration_requires_complete_payload_and_rejects_managed_service(self):
        project = Project.objects.create(name="Oily", slug="oily")
        adopted = Service.objects.create(
            project=project,
            name="backend",
            unit_name="oily-backend.service",
            lifecycle_state=Service.LIFECYCLE_ADOPTED,
            target_server=self.server,
        )
        partial = self.client.put(
            f"/api/control/v1/services/{adopted.public_id}/deployment-configuration/",
            {"repository": "https://github.com/example/oily.git"},
            format="json",
        )
        self.assertEqual(partial.status_code, 400)

        managed = Service.objects.create(
            project=project,
            name="web",
            unit_name="oily-web.service",
            lifecycle_state=Service.LIFECYCLE_MANAGED,
            repository="https://github.com/example/oily.git",
            branch="main",
            root_directory=".",
            runtime="node-nextjs",
            service_port=3000,
            target_server=self.server,
        )
        response = self.client.put(
            f"/api/control/v1/services/{managed.public_id}/deployment-configuration/",
            {
                "repository": "https://github.com/example/oily.git",
                "branch": "main",
                "root_directory": ".",
                "runtime": "node-nextjs",
                "install_configuration": {},
                "build_configuration": {},
                "service_port": 3000,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "invalid_service_lifecycle")

    def test_protected_unit_can_be_adopted_but_restart_policy_stays_blocked(self):
        project = Project.objects.create(name="Platform", slug="platform")
        unit = "digitalafarin-platform-web.service"
        ServiceSnapshot.objects.create(
            server=self.server,
            unit_name=unit,
            description="Platform Web",
            load_state="loaded",
            active_state="active",
            sub_state="running",
        )
        adopted = self.client.post(
            f"/api/control/v1/projects/{project.public_id}/services/adopt/",
            {
                "server_id": str(self.server.public_id),
                "unit_name": unit,
                "name": "web",
            },
            format="json",
        )
        self.assertEqual(adopted.status_code, 201)
        before = Operation.objects.count()
        restart = self.client.post(
            "/api/control/v1/operations/",
            {
                "server_id": str(self.server.public_id),
                "kind": "service.restart",
                "payload": {"unit_name": unit},
            },
            format="json",
        )
        self.assertEqual(restart.status_code, 400)
        self.assertEqual(Operation.objects.count(), before)

    def test_health_check_and_deployment_event_have_uuid_identity(self):
        project = Project.objects.create(name="Oily", slug="oily")
        service = Service.objects.create(
            project=project,
            name="web",
            unit_name="oily-web.service",
            lifecycle_state=Service.LIFECYCLE_MANAGED,
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
