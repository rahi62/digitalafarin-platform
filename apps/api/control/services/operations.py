import json
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from control.models import AuditEvent, Operation, Server


class OperationTransitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaimedOperation:
    operation: Operation
    claim_token: str


def _audit(operation: Operation, from_state: str | None, to_state: str) -> None:
    AuditEvent.objects.create(
        event_type="operation.transition",
        target_type="operation",
        target_id=str(operation.public_id),
        actor=operation.actor,
        metadata={
            "operation_id": str(operation.public_id),
            "kind": operation.kind,
            "server_id": str(operation.server.public_id),
            "from_state": from_state,
            "to_state": to_state,
        },
    )


@transaction.atomic
def create_operation(
    *,
    server: Server,
    kind: str,
    payload: dict,
    actor: str,
    idempotency_key: str = "",
) -> Operation:
    if idempotency_key:
        existing = Operation.objects.filter(
            server=server, actor=actor, idempotency_key=idempotency_key
        ).first()
        if existing:
            return existing
    operation = Operation.objects.create(
        server=server,
        kind=kind,
        payload=payload,
        actor=actor,
        idempotency_key=idempotency_key,
    )
    _audit(operation, None, Operation.STATE_QUEUED)
    return operation


@transaction.atomic
def claim_next_operation(
    *, server: Server, lease_seconds: int = 60
) -> ClaimedOperation | None:
    # Serialize claims per host, including on PostgreSQL with multiple API workers.
    Server.objects.select_for_update().get(pk=server.pk)
    now = timezone.now()
    Operation.objects.filter(
        server=server,
        state=Operation.STATE_CLAIMED,
        lease_expires_at__lte=now,
    ).update(
        state=Operation.STATE_QUEUED,
        claim_token="",
        lease_expires_at=None,
        claimed_at=None,
    )
    if Operation.objects.filter(server=server, state__in=[Operation.STATE_CLAIMED, Operation.STATE_RUNNING]).exists():
        return None
    operation = (
        Operation.objects.select_for_update()
        .filter(server=server, state=Operation.STATE_QUEUED)
        .order_by("created_at")
        .first()
    )
    if operation is None:
        return None
    token = secrets.token_urlsafe(32)
    operation.state = Operation.STATE_CLAIMED
    operation.claim_token = token
    operation.claimed_at = now
    operation.lease_expires_at = now + timedelta(seconds=max(15, lease_seconds))
    operation.save(
        update_fields=[
            "state",
            "claim_token",
            "claimed_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    _audit(operation, Operation.STATE_QUEUED, Operation.STATE_CLAIMED)
    return ClaimedOperation(operation=operation, claim_token=token)


def _locked_operation(operation_id, server: Server, claim_token: str) -> Operation:
    try:
        operation = Operation.objects.select_for_update().get(
            public_id=operation_id, server=server
        )
    except Operation.DoesNotExist as exc:
        raise OperationTransitionError("operation not found") from exc
    if not operation.claim_token or not secrets.compare_digest(
        operation.claim_token, claim_token
    ):
        raise OperationTransitionError("invalid claim token")
    return operation


@transaction.atomic
def start_operation(*, operation_id, server: Server, claim_token: str) -> Operation:
    operation = _locked_operation(operation_id, server, claim_token)
    if operation.state == Operation.STATE_RUNNING:
        return operation
    if operation.state != Operation.STATE_CLAIMED:
        raise OperationTransitionError("operation is not claimed")
    if operation.lease_expires_at and operation.lease_expires_at <= timezone.now():
        raise OperationTransitionError("operation claim expired")
    operation.state = Operation.STATE_RUNNING
    operation.started_at = timezone.now()
    operation.save(update_fields=["state", "started_at", "updated_at"])
    _audit(operation, Operation.STATE_CLAIMED, Operation.STATE_RUNNING)
    return operation


def _bounded_json(value: dict, limit: int = 65536) -> dict:
    encoded = json.dumps(value, default=str)
    if len(encoded.encode("utf-8")) > limit:
        return {"message": "result truncated", "truncated": True}
    return value


@transaction.atomic
def report_progress(*, operation_id, server, claim_token, sequence, stage):
    operation = _locked_operation(operation_id, server, claim_token)
    if operation.state != Operation.STATE_RUNNING:
        raise OperationTransitionError('operation is not running')
    now = timezone.now()
    if sequence > operation.progress_sequence:
        operation.progress = {'stage': stage, 'reported_at': now.isoformat()}
        operation.progress_sequence = sequence
    operation.lease_expires_at = now + timedelta(seconds=60)
    operation.save(update_fields=['progress', 'progress_sequence', 'lease_expires_at', 'updated_at'])
    return operation


@transaction.atomic
def complete_operation(
    *,
    operation_id,
    server: Server,
    claim_token: str,
    succeeded: bool,
    result: dict | None = None,
    error_code: str = "",
    error_message: str = "",
) -> Operation:
    operation = _locked_operation(operation_id, server, claim_token)
    target = Operation.STATE_SUCCEEDED if succeeded else Operation.STATE_FAILED
    if operation.state == target:
        return operation
    if operation.state != Operation.STATE_RUNNING:
        raise OperationTransitionError("operation is not running")
    operation.state = target
    operation.result = _bounded_json(result or {})
    operation.error_code = error_code[:100]
    operation.error_message = error_message[:500]
    operation.completed_at = timezone.now()
    operation.lease_expires_at = None
    operation.save(
        update_fields=[
            "state",
            "result",
            "error_code",
            "error_message",
            "completed_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    _audit(operation, Operation.STATE_RUNNING, target)
    return operation
