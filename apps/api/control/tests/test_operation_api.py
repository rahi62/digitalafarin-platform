from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import (
    AgentCredential,
    Operation,
    Server,
    ServiceCredential,
    ServicePrincipal,
    ServiceSnapshot,
)
from control.security import issue_secret


class OperationAPITests(TestCase):
    def test_progress_renews_lease_and_rejects_wrong_claim(self):
        self.create_operation()
        claim = self.agent.post('/api/agent/v1/operations/claim', {}, format='json').json()
        operation_id = claim['operation']['id']
        token = claim['claim_token']
        self.agent.post(f'/api/agent/v1/operations/{operation_id}/started', {'claim_token': token}, format='json')
        url = f'/api/agent/v1/operations/{operation_id}/progress'
        data = {'claim_token': token, 'sequence': 1, 'stage': 'building'}
        self.assertEqual(self.agent.post(url, {**data, 'claim_token': 'wrong'}, format='json').status_code, 409)
        self.assertEqual(self.agent.post(url, data, format='json').status_code, 200)
        operation = Operation.objects.get(public_id=operation_id)
        self.assertEqual(operation.progress['stage'], 'building')
        self.assertGreater(operation.lease_expires_at, timezone.now())
        self.assertEqual(self.agent.post(url, {**data, 'sequence': 0, 'stage': 'preparing'}, format='json').status_code, 200)
        operation.refresh_from_db()
        self.assertEqual(operation.progress['stage'], 'building')
        self.assertEqual(self.agent.post(url, {**data, 'stage': 'password=secret'}, format='json').status_code, 400)

    def setUp(self):
        self.server = Server.objects.create(
            name="Worker",
            hostname="worker",
            last_seen_at=timezone.now(),
        )
        for unit in ("oily-api.service", "digitalafarin-platform-api.service"):
            ServiceSnapshot.objects.create(
                server=self.server,
                unit_name=unit,
                load_state="loaded",
                active_state="active",
                sub_state="running",
            )
        self.principal = ServicePrincipal.objects.create(
            name="operator",
            scopes=["operations:create", "operations:read", "logs:read"],
        )
        service_secret = issue_secret("service")
        ServiceCredential.objects.create(
            principal=self.principal,
            token_prefix=service_secret.prefix,
            token_hash=service_secret.digest,
        )
        self.control = APIClient()
        self.control.credentials(
            HTTP_AUTHORIZATION=f"Bearer {service_secret.cleartext}"
        )

        agent_secret = issue_secret("agent")
        AgentCredential.objects.create(
            server=self.server,
            token_prefix=agent_secret.prefix,
            token_hash=agent_secret.digest,
        )
        self.agent = APIClient()
        self.agent.credentials(HTTP_AUTHORIZATION=f"Bearer {agent_secret.cleartext}")

    def create_operation(self, kind="service.restart", payload=None):
        return self.control.post(
            "/api/control/v1/operations/",
            {
                "server_id": str(self.server.public_id),
                "kind": kind,
                "payload": payload or {"unit_name": "oily-api.service"},
                "idempotency_key": "ui-request-1",
            },
            format="json",
        )

    def test_create_claim_start_and_complete_is_server_bound(self):
        created = self.create_operation()
        self.assertEqual(created.status_code, 201)
        operation_id = created.json()["id"]

        claimed = self.agent.post("/api/agent/v1/operations/claim", {}, format="json")
        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(claimed.json()["operation"]["id"], operation_id)
        token = claimed.json()["claim_token"]

        started = self.agent.post(
            f"/api/agent/v1/operations/{operation_id}/started",
            {"claim_token": token},
            format="json",
        )
        self.assertEqual(started.status_code, 200)
        completed = self.agent.post(
            f"/api/agent/v1/operations/{operation_id}/complete",
            {"claim_token": token, "succeeded": True, "result": {"message": "ok"}},
            format="json",
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["state"], "succeeded")

    def test_create_rejects_protected_unknown_and_arbitrary_payloads(self):
        protected = self.create_operation(
            payload={"unit_name": "digitalafarin-platform-api.service"}
        )
        unknown = self.create_operation(kind="shell.execute", payload={"command": "id"})
        extra = self.create_operation(payload={"unit_name": "oily-api.service", "args": ["--force"]})

        self.assertEqual(protected.status_code, 400)
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(extra.status_code, 400)
        self.assertEqual(Operation.objects.count(), 0)


    def test_bootstrap_operation_accepts_only_empty_typed_payload_and_is_idempotent(self):
        first = self.control.post(
            "/api/control/v1/operations/",
            {
                "server_id": str(self.server.public_id),
                "kind": "server.bootstrap",
                "payload": {},
                "idempotency_key": "bootstrap-1",
            },
            format="json",
        )
        second = self.control.post(
            "/api/control/v1/operations/",
            {
                "server_id": str(self.server.public_id),
                "kind": "server.bootstrap",
                "payload": {},
                "idempotency_key": "bootstrap-1",
            },
            format="json",
        )
        invalid = self.control.post(
            "/api/control/v1/operations/",
            {
                "server_id": str(self.server.public_id),
                "kind": "server.bootstrap",
                "payload": {"command": "id"},
            },
            format="json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(Operation.objects.filter(kind="server.bootstrap").count(), 1)

    def test_log_bounds_and_log_scope_are_enforced(self):
        invalid = self.create_operation(
            kind="service.logs",
            payload={"unit_name": "oily-api.service", "lines": 201},
        )
        self.assertEqual(invalid.status_code, 400)

        created = self.create_operation(
            kind="service.logs",
            payload={"unit_name": "oily-api.service", "lines": 20},
        )
        operation = Operation.objects.get(public_id=created.json()["id"])
        operation.result = {"logs": "redacted output"}
        operation.state = Operation.STATE_SUCCEEDED
        operation.save(update_fields=["result", "state"])
        self.principal.scopes = ["operations:read"]
        self.principal.save(update_fields=["scopes"])

        response = self.control.get(f"/api/control/v1/operations/{operation.public_id}/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("result", response.json())

    def test_create_scope_and_fresh_server_are_required(self):
        self.principal.scopes = ["operations:read"]
        self.principal.save(update_fields=["scopes"])
        self.assertEqual(self.create_operation().status_code, 403)

        self.principal.scopes = ["operations:create"]
        self.principal.save(update_fields=["scopes"])
        self.server.last_seen_at = timezone.now() - timedelta(seconds=121)
        self.server.save(update_fields=["last_seen_at"])
        response = self.create_operation()
        self.assertEqual(response.status_code, 409)
