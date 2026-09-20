import os

from cryptography.fernet import Fernet
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import AgentCredential, DatabaseResource, Operation, Project, Server, Service, ServiceCredential, ServicePrincipal
from control.security import issue_secret


class DatabaseResourceAPITests(TestCase):
    def setUp(self):
        self.old = os.environ.get("PLATFORM_SECRET_KEYS")
        os.environ["PLATFORM_SECRET_KEYS"] = Fernet.generate_key().decode()
        self.server = Server.objects.create(name="Target", last_seen_at=timezone.now())
        self.project = Project.objects.create(name="Oily", slug="oily")
        self.service = Service.objects.create(
            project=self.project,
            name="backend",
            unit_name="oily-backend.service",
            lifecycle_state=Service.LIFECYCLE_MANAGED,
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

    def tearDown(self):
        if self.old is None:
            os.environ.pop("PLATFORM_SECRET_KEYS", None)
        else:
            os.environ["PLATFORM_SECRET_KEYS"] = self.old

    def test_create_generates_encrypted_credential_and_queues_reference_only(self):
        response = self.client.post(
            f"/api/control/v1/projects/{self.project.public_id}/databases/",
            {"service_id": str(self.service.public_id), "database_name": "oily", "username": "oily_app"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        database = DatabaseResource.objects.get()
        operation = Operation.objects.get(public_id=response.json()["operation_id"])
        self.assertTrue(database.password_ciphertext.startswith("v1:"))
        self.assertEqual(operation.payload, {"database_resource_id": str(database.public_id)})
        self.assertNotIn("password", str(response.json()).lower())

    def test_restore_accepts_only_managed_backup_name(self):
        database = DatabaseResource.objects.create(
            project=self.project,
            service=self.service,
            server=self.server,
            database_name="oily",
            username="oily_app",
            password_ciphertext="v1:not-used",
        )
        rejected = self.client.post(
            f"/api/control/v1/databases/{database.public_id}/restore/",
            {"backup_name": "../../etc/passwd", "sql": "DROP DATABASE oily"},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)

    def test_generated_password_is_only_revealed_to_bound_agent_claim(self):
        create = self.client.post(
            f"/api/control/v1/projects/{self.project.public_id}/databases/",
            {"service_id": str(self.service.public_id), "database_name": "oily", "username": "oily_app"},
            format="json",
        )
        agent_secret = issue_secret("agent")
        AgentCredential.objects.create(
            server=self.server,
            token_prefix=agent_secret.prefix,
            token_hash=agent_secret.digest,
        )
        agent = APIClient()
        agent.credentials(HTTP_AUTHORIZATION=f"Bearer {agent_secret.cleartext}")

        claimed = agent.post("/api/agent/v1/operations/claim", {}, format="json")

        self.assertEqual(claimed.status_code, 200)
        self.assertIn("password", claimed.json()["operation"]["execution"])
        operation = Operation.objects.get(public_id=create.json()["operation_id"])
        self.assertNotIn("password", str(operation.payload).lower())
