from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from control.models import AuditEvent, Operation, Server
from control.services.operations import (
    OperationTransitionError,
    claim_next_operation,
    complete_operation,
    create_operation,
    start_operation,
)


class OperationLifecycleTests(TestCase):
    def test_server_does_not_claim_another_operation_while_running(self):
        for index in range(2):
            create_operation(server=self.server, kind='server.bootstrap', payload={}, actor='operator')
        first = claim_next_operation(server=self.server)
        self.assertIsNone(claim_next_operation(server=self.server))
        start_operation(operation_id=first.operation.public_id, server=self.server, claim_token=first.claim_token)
        self.assertIsNone(claim_next_operation(server=self.server))
        complete_operation(operation_id=first.operation.public_id, server=self.server, claim_token=first.claim_token, succeeded=True)
        self.assertIsNotNone(claim_next_operation(server=self.server))

    def setUp(self):
        self.server = Server.objects.create(name="Worker", hostname="worker")

    def test_operation_follows_audited_lifecycle(self):
        operation = create_operation(
            server=self.server,
            kind="service.restart",
            payload={"unit_name": "oily-api.service"},
            actor="operator",
        )

        self.assertEqual(operation.state, Operation.STATE_QUEUED)
        claimed = claim_next_operation(server=self.server)
        self.assertEqual(claimed.operation.state, Operation.STATE_CLAIMED)
        started = start_operation(
            operation_id=operation.public_id,
            server=self.server,
            claim_token=claimed.claim_token,
        )
        self.assertEqual(started.state, Operation.STATE_RUNNING)
        completed = complete_operation(
            operation_id=operation.public_id,
            server=self.server,
            claim_token=claimed.claim_token,
            succeeded=True,
            result={"message": "restarted"},
        )
        self.assertEqual(completed.state, Operation.STATE_SUCCEEDED)
        self.assertEqual(
            list(
                AuditEvent.objects.filter(target_id=str(operation.public_id))
                .order_by("created_at")
                .values_list("metadata__to_state", flat=True)
            ),
            ["queued", "claimed", "running", "succeeded"],
        )

    def test_wrong_server_and_illegal_terminal_transition_are_rejected(self):
        operation = create_operation(
            server=self.server,
            kind="service.stop",
            payload={"unit_name": "oily-api.service"},
            actor="operator",
        )
        other = Server.objects.create(name="Other")
        with self.assertRaises(OperationTransitionError):
            start_operation(
                operation_id=operation.public_id,
                server=other,
                claim_token="wrong",
            )

        claimed = claim_next_operation(server=self.server)
        start_operation(
            operation_id=operation.public_id,
            server=self.server,
            claim_token=claimed.claim_token,
        )
        complete_operation(
            operation_id=operation.public_id,
            server=self.server,
            claim_token=claimed.claim_token,
            succeeded=False,
            error_code="systemd_failed",
            error_message="failure",
        )
        with self.assertRaises(OperationTransitionError):
            complete_operation(
                operation_id=operation.public_id,
                server=self.server,
                claim_token=claimed.claim_token,
                succeeded=True,
            )

    def test_expired_claim_is_requeued_and_can_be_claimed_again(self):
        operation = create_operation(
            server=self.server,
            kind="service.start",
            payload={"unit_name": "oily-api.service"},
            actor="operator",
        )
        first = claim_next_operation(server=self.server)
        Operation.objects.filter(pk=operation.pk).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )

        second = claim_next_operation(server=self.server)

        self.assertEqual(second.operation.public_id, operation.public_id)
        self.assertNotEqual(second.claim_token, first.claim_token)

    def test_idempotency_key_returns_existing_operation(self):
        first = create_operation(
            server=self.server,
            kind="service.logs",
            payload={"unit_name": "oily-api.service", "lines": 20},
            actor="operator",
            idempotency_key="request-1",
        )
        second = create_operation(
            server=self.server,
            kind="service.logs",
            payload={"unit_name": "oily-api.service", "lines": 20},
            actor="operator",
            idempotency_key="request-1",
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Operation.objects.count(), 1)
