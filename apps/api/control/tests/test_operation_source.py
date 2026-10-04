from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from control.models import AgentCredential, Deployment, Operation, Project, Server, Service
from control.security import issue_secret
from control.services.execution import build_execution_context


class OperationSourceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.server = Server.objects.create(name="server")
        issued = issue_secret("agent")
        AgentCredential.objects.create(server=self.server, token_prefix=issued.prefix, token_hash=issued.digest)
        self.token = issued.cleartext
        project = Project.objects.create(name="Project", slug="project")
        self.service = Service.objects.create(
            project=project, name="web", unit_name="web.service", target_server=self.server,
            repository="https://github.com/example/repo.git", branch="main",
        )
        deployment = Deployment.objects.create(
            service=self.service, requested_ref="a" * 40, resolved_commit="a" * 40, requested_by="test"
        )
        self.operation = Operation.objects.create(
            server=self.server, kind=Operation.KIND_DEPLOYMENT_DEPLOY, state=Operation.STATE_RUNNING,
            payload={"deployment_id": str(deployment.public_id)}, actor="test", claim_token="claim",
        )
        self.url = f"/api/agent/v1/operations/{self.operation.public_id}/source"

    @patch("control.agent_views.download_bundle", return_value=b"bundle")
    def test_running_claimed_operation_can_download_bound_source(self, download):
        response = self.client.get(
            self.url, HTTP_AUTHORIZATION=f"Bearer {self.token}", HTTP_X_DIGITALAFARIN_CLAIM="claim"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"bundle")
        self.assertEqual(response["X-DigitalAfarin-Commit"], "a" * 40)
        download.assert_called_once_with("https://github.com/example/repo.git", "a" * 40)

    @patch("control.agent_views.download_bundle")
    def test_wrong_claim_is_rejected_before_github(self, download):
        response = self.client.get(
            self.url, HTTP_AUTHORIZATION=f"Bearer {self.token}", HTTP_X_DIGITALAFARIN_CLAIM="wrong"
        )
        self.assertEqual(response.status_code, 403)
        download.assert_not_called()

    @patch("control.agent_views.download_bundle")
    def test_completed_operation_cannot_download_source(self, download):
        self.operation.state = Operation.STATE_SUCCEEDED
        self.operation.save(update_fields=["state"])
        response = self.client.get(
            self.url, HTTP_AUTHORIZATION=f"Bearer {self.token}", HTTP_X_DIGITALAFARIN_CLAIM="claim"
        )
        self.assertEqual(response.status_code, 404)
        download.assert_not_called()

    def test_only_protected_platform_service_uses_trusted_local_source(self):
        self.assertNotIn("source_transport", build_execution_context(self.operation))
        self.service.project.slug = "digitalafarin-platform"
        self.service.project.save(update_fields=["slug"])
        self.service.name = "platform-web"
        self.service.unit_name = "digitalafarin-platform-web.service"
        self.service.save(update_fields=["name", "unit_name"])
        self.assertEqual(build_execution_context(self.operation)["source_transport"], "trusted_local")
