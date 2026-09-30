import os

from cryptography.fernet import Fernet
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import AgentCredential, Deployment, EnvironmentVariable, HealthCheck, Operation, Project, Release, Server, Service, ServiceCredential, ServicePrincipal
from control.security import issue_secret


class DeploymentActionTests(TestCase):
    def setUp(self):
        self.old_keys = os.environ.get("PLATFORM_SECRET_KEYS")
        os.environ["PLATFORM_SECRET_KEYS"] = Fernet.generate_key().decode()
        self.server = Server.objects.create(name="Target", last_seen_at=timezone.now(), disk_percent=25)
        self.project = Project.objects.create(name="Oily", slug="oily")
        self.service = Service.objects.create(
            project=self.project, name="web", unit_name="oily-web.service", repository="https://github.com/example/oily.git",
            lifecycle_state=Service.LIFECYCLE_MANAGED,
            branch="main", runtime="node-nextjs", service_port=3000, target_server=self.server,
        )
        principal = ServicePrincipal.objects.create(name="web", scopes=["operations:create", "operations:read"])
        issued = issue_secret("service")
        ServiceCredential.objects.create(principal=principal, token_prefix=issued.prefix, token_hash=issued.digest)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")

    def tearDown(self):
        if self.old_keys is None:
            os.environ.pop("PLATFORM_SECRET_KEYS", None)
        else:
            os.environ["PLATFORM_SECRET_KEYS"] = self.old_keys

    def test_adopted_and_configured_services_cannot_deploy(self):
        for state in [Service.LIFECYCLE_ADOPTED, Service.LIFECYCLE_CONFIGURED]:
            self.service.lifecycle_state = state
            self.service.save(update_fields=["lifecycle_state"])
            response = self.client.post(
                f"/api/control/v1/services/{self.service.public_id}/deployments/",
                {},
                format="json",
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["error"], "service_not_managed")
            self.assertEqual(Operation.objects.count(), 0)
            self.assertEqual(Deployment.objects.count(), 0)

    def test_redeploy_and_rollback_are_blocked_when_source_service_is_not_managed(self):
        source = Deployment.objects.create(
            service=self.service,
            requested_ref="main",
            resolved_commit="b" * 40,
            requested_by="operator",
            state="succeeded",
        )
        release = Release.objects.create(
            service=self.service,
            deployment=source,
            name="release-one",
            exact_commit="b" * 40,
            path="/srv/digitalafarin/apps/oily/web/releases/release-one",
        )
        source.active_release = release
        source.save(update_fields=["active_release"])
        self.service.lifecycle_state = Service.LIFECYCLE_CONFIGURED
        self.service.save(update_fields=["lifecycle_state"])

        redeploy = self.client.post(
            f"/api/control/v1/deployments/{source.public_id}/redeploy/",
            {},
            format="json",
        )
        rollback = self.client.post(
            f"/api/control/v1/deployments/{source.public_id}/rollback/",
            {},
            format="json",
        )

        self.assertEqual(redeploy.status_code, 409)
        self.assertEqual(redeploy.json()["error"], "service_not_managed")
        self.assertEqual(rollback.status_code, 409)
        self.assertEqual(rollback.json()["error"], "service_not_managed")
        self.assertEqual(Operation.objects.count(), 0)
        self.assertEqual(Deployment.objects.count(), 1)

    def test_exact_commit_deploy_creates_deployment_event_and_typed_operation(self):
        commit = "a" * 40
        response = self.client.post(
            f"/api/control/v1/services/{self.service.public_id}/deployments/",
            {"commit": commit},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        deployment = Deployment.objects.get(public_id=response.json()["id"])
        self.assertEqual(deployment.resolved_commit, commit)
        self.assertEqual(list(deployment.events.values_list("state", flat=True)), ["queued"])
        operation = Operation.objects.get(payload__deployment_id=str(deployment.public_id))
        self.assertEqual(operation.kind, "deployment.deploy")

    def test_deploy_latest_uses_configured_branch_and_disk_guardrail(self):
        response = self.client.post(
            f"/api/control/v1/services/{self.service.public_id}/deployments/", {}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Deployment.objects.get().requested_ref, "main")

        self.server.disk_percent = 90
        self.server.save(update_fields=["disk_percent"])
        blocked = self.client.post(
            f"/api/control/v1/services/{self.service.public_id}/deployments/", {}, format="json"
        )
        self.assertEqual(blocked.status_code, 409)

    def test_redeploy_uses_existing_exact_commit_and_rollback_uses_release(self):
        original = Deployment.objects.create(
            service=self.service,
            requested_ref="main",
            resolved_commit="b" * 40,
            requested_by="operator",
            state="succeeded",
        )
        release = Release.objects.create(
            service=self.service,
            deployment=original,
            name="release-one",
            exact_commit="b" * 40,
            path="/srv/digitalafarin/apps/oily/web/releases/release-one",
        )
        original.active_release = release
        original.save(update_fields=["active_release"])

        redeploy = self.client.post(
            f"/api/control/v1/deployments/{original.public_id}/redeploy/", {}, format="json"
        )
        rollback = self.client.post(
            f"/api/control/v1/deployments/{original.public_id}/rollback/", {}, format="json"
        )

        self.assertEqual(redeploy.status_code, 201)
        self.assertEqual(Deployment.objects.get(public_id=redeploy.json()["id"]).requested_ref, "b" * 40)
        self.assertEqual(rollback.status_code, 201)
        self.assertEqual(Operation.objects.get(public_id=rollback.json()["operation_id"]).kind, "deployment.rollback")

    def test_agent_claim_receives_execution_context_without_persisting_secret(self):
        from control.services.secrets import encrypt_secret

        self.service.unit_name = "custom-existing-oily.service"
        self.service.save(update_fields=["unit_name"])
        EnvironmentVariable.objects.create(
            project=self.project,
            service=self.service,
            key="APP_SECRET",
            value_type="secret",
            scope="service",
            secret_ciphertext=encrypt_secret("deployment-sentinel"),
        )
        HealthCheck.objects.create(service=self.service, path="/health")
        created = self.client.post(
            f"/api/control/v1/services/{self.service.public_id}/deployments/",
            {"commit": "d" * 40},
            format="json",
        )
        issued = issue_secret("agent")
        AgentCredential.objects.create(server=self.server, token_prefix=issued.prefix, token_hash=issued.digest)
        agent = APIClient()
        agent.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")

        claim = agent.post("/api/agent/v1/operations/claim", {}, format="json")

        execution = claim.json()["operation"]["execution"]
        self.assertEqual(execution["environment"]["APP_SECRET"], "deployment-sentinel")
        self.assertEqual(execution["unit_name"], "custom-existing-oily.service")
        operation = Operation.objects.get(public_id=created.json()["operation_id"])
        self.assertNotIn("deployment-sentinel", str(operation.payload))

    def test_agent_completion_persists_deployment_events_and_active_release(self):
        created = self.client.post(
            f"/api/control/v1/services/{self.service.public_id}/deployments/",
            {"commit": "e" * 40},
            format="json",
        )
        issued = issue_secret("agent")
        AgentCredential.objects.create(server=self.server, token_prefix=issued.prefix, token_hash=issued.digest)
        agent = APIClient()
        agent.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")
        claim = agent.post("/api/agent/v1/operations/claim", {}, format="json").json()
        operation_id = claim["operation"]["id"]
        token = claim["claim_token"]
        agent.post(f"/api/agent/v1/operations/{operation_id}/started", {"claim_token": token}, format="json")

        completed = agent.post(
            f"/api/agent/v1/operations/{operation_id}/complete",
            {
                "claim_token": token,
                "succeeded": True,
                "result": {
                    "deployment_id": created.json()["id"],
                    "final_state": "succeeded",
                    "release_name": "20260915-183015-eeeeeee",
                    "exact_commit": "e" * 40,
                    "events": [
                        {"state": state, "message": state}
                        for state in ["preparing", "cloning", "building", "releasing", "health_check", "activating", "verifying", "succeeded"]
                    ],
                },
            },
            format="json",
        )

        self.assertEqual(completed.status_code, 200)
        deployment = Deployment.objects.get(public_id=created.json()["id"])
        self.assertEqual(deployment.state, "succeeded")
        self.assertEqual(deployment.active_release.exact_commit, "e" * 40)
        self.assertEqual(deployment.events.count(), 9)

        repeated = agent.post(
            f"/api/agent/v1/operations/{operation_id}/complete",
            {"claim_token": token, "succeeded": True, "result": Operation.objects.get(public_id=operation_id).result},
            format="json",
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(deployment.events.count(), 9)
        self.assertEqual(Release.objects.count(), 1)

    def test_invalid_claim_cannot_fail_deployment(self):
        created = self.client.post(
            f"/api/control/v1/services/{self.service.public_id}/deployments/",
            {"commit": "e" * 40}, format="json",
        ).json()
        issued = issue_secret("agent")
        AgentCredential.objects.create(server=self.server, token_prefix=issued.prefix, token_hash=issued.digest)
        agent = APIClient()
        agent.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")
        claim = agent.post("/api/agent/v1/operations/claim", {}, format="json").json()
        operation_id = claim["operation"]["id"]
        agent.post(f"/api/agent/v1/operations/{operation_id}/started", {"claim_token": claim["claim_token"]}, format="json")
        response = agent.post(
            f"/api/agent/v1/operations/{operation_id}/complete",
            {"claim_token": "invalid-claim", "succeeded": False, "error_code": "fake_failure"}, format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Deployment.objects.get(public_id=created['id']).state, 'queued')
        self.assertEqual(Operation.objects.get(public_id=operation_id).state, 'running')

    def test_invalid_result_rolls_back_operation_completion(self):
        created = self.client.post(
            f"/api/control/v1/services/{self.service.public_id}/deployments/",
            {"commit": "e" * 40}, format="json",
        ).json()
        issued = issue_secret("agent")
        AgentCredential.objects.create(server=self.server, token_prefix=issued.prefix, token_hash=issued.digest)
        agent = APIClient()
        agent.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")
        claim = agent.post("/api/agent/v1/operations/claim", {}, format="json").json()
        operation_id = claim["operation"]["id"]
        agent.post(f"/api/agent/v1/operations/{operation_id}/started", {"claim_token": claim["claim_token"]}, format="json")
        response = agent.post(
            f"/api/agent/v1/operations/{operation_id}/complete",
            {"claim_token": claim["claim_token"], "succeeded": True, "result": {"events": [], "final_state": "succeeded"}}, format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Operation.objects.get(public_id=operation_id).state, 'running')
        self.assertEqual(Deployment.objects.get(public_id=created['id']).state, 'queued')
