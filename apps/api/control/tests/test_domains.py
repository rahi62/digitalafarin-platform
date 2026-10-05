from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import Domain, Operation, Project, Server, Service, ServiceCredential, ServicePrincipal
from control.security import issue_secret


class DomainAPITests(TestCase):
    def setUp(self):
        server = Server.objects.create(name="Target", last_seen_at=timezone.now())
        self.project = Project.objects.create(name="Oily", slug="oily")
        self.service = Service.objects.create(
            project=self.project, name="web", unit_name="oily-web.service", repository="https://github.com/example/oily.git",
            lifecycle_state=Service.LIFECYCLE_MANAGED,
            branch="main", runtime="node-nextjs", service_port=3000, target_server=server,
        )
        principal = ServicePrincipal.objects.create(name="web", scopes=["operations:create", "operations:read"])
        issued = issue_secret("service")
        ServiceCredential.objects.create(principal=principal, token_prefix=issued.prefix, token_hash=issued.digest)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")

    def test_domain_creation_queues_typed_configuration(self):
        response = self.client.post(
            f"/api/control/v1/projects/{self.project.public_id}/domains/",
            {"service_id": str(self.service.public_id), "hostname": "app.example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        domain = Domain.objects.get()
        operation = Operation.objects.get(public_id=response.json()["operation_id"])
        self.assertEqual(operation.kind, "domain.configure")
        self.assertEqual(operation.payload, {"domain_id": str(domain.public_id)})

    def test_domain_rejects_ports_config_text_and_invalid_hostname(self):
        response = self.client.post(
            f"/api/control/v1/projects/{self.project.public_id}/domains/",
            {"service_id": str(self.service.public_id), "hostname": "bad;example", "port": 22, "nginx": "server {}"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


    def test_external_domain_is_metadata_only(self):
        response = self.client.post(
            f"/api/control/v1/projects/{self.project.public_id}/domains/",
            {
                "service_id": str(self.service.public_id),
                "hostname": "cafeno.digitalafarin.ir",
                "configure_nginx": False,
                "ssl_enabled": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "external")
        self.assertEqual(body["management_mode"], "external")
        self.assertTrue(body["ssl_enabled"])
        self.assertNotIn("operation_id", body)
        self.assertEqual(Operation.objects.count(), 0)
