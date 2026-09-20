from pathlib import PurePosixPath

from django.db import IntegrityError, transaction

from django.utils import timezone

from control.models import AuditEvent, Operation, Release, Service, ServiceTakeover
from control.services.execution import build_health_check_context
from control.services.operations import create_operation


class TakeoverError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _require_prepare_eligible(service: Service) -> bool:
    if service.lifecycle_state != Service.LIFECYCLE_CONFIGURED:
        raise TakeoverError(
            "service_not_configured",
            "Service must be configured before controlled takeover.",
        )
    if service.executor != Service.EXECUTOR_SYSTEMD or service.runtime != Service.RUNTIME_NODE:
        raise TakeoverError(
            "unsupported_takeover_runtime",
            "Stage B3 supports node-nextjs on systemd only.",
        )
    required = {
        "repository": service.repository,
        "branch": service.branch,
        "root_directory": service.root_directory,
        "service_port": service.service_port,
        "unit_name": service.unit_name,
    }
    if any(value in {None, ""} for value in required.values()):
        raise TakeoverError(
            "service_configuration_incomplete",
            "Service deployment metadata is incomplete.",
        )
    if not service.target_server.services.filter(unit_name=service.unit_name).exists():
        raise TakeoverError(
            "inventory_unit_missing",
            "Configured systemd unit is missing from current inventory.",
        )
    if service.target_server.status != "online":
        raise TakeoverError(
            "server_offline",
            "Target server must have fresh telemetry.",
        )
    if service.target_server.disk_percent >= 90:
        raise TakeoverError(
            "disk_usage_blocked",
            "Disk usage blocks controlled takeover.",
        )
    return service.target_server.disk_percent >= 80


@transaction.atomic
def queue_takeover_prepare(
    *, service: Service, exact_commit: str, requested_by: str
) -> tuple[ServiceTakeover, Operation]:
    disk_warning = _require_prepare_eligible(service)
    if ServiceTakeover.objects.filter(
        service=service,
        state__in=ServiceTakeover.ACTIVE_STATES,
    ).exists():
        raise TakeoverError(
            "takeover_already_active",
            "A controlled takeover is already active for this service.",
        )
    try:
        takeover = ServiceTakeover.objects.create(
            service=service,
            requested_commit=exact_commit,
            requested_by=requested_by,
            health_check_snapshot=build_health_check_context(service),
        )
    except IntegrityError as exc:
        raise TakeoverError(
            "takeover_already_active",
            "A controlled takeover is already active for this service.",
        ) from exc

    operation = create_operation(
        server=service.target_server,
        kind=Operation.KIND_TAKEOVER_PREPARE,
        payload={"takeover_id": str(takeover.public_id)},
        actor=requested_by,
    )
    takeover.prepare_operation = operation
    takeover.save(update_fields=["prepare_operation", "updated_at"])

    AuditEvent.objects.create(
        event_type="service.takeover.requested",
        target_type="service_takeover",
        target_id=str(takeover.public_id),
        actor=requested_by,
        metadata={
            "service_id": str(service.public_id),
            "server_id": str(service.target_server.public_id),
            "unit_name": service.unit_name,
            "exact_commit": exact_commit,
            "disk_warning": disk_warning,
        },
    )
    return takeover, operation


# Takeover state transitions are deliberately narrower than Deployment transitions.
TAKEOVER_NEXT_STATES = {
    ServiceTakeover.STATE_QUEUED: {
        ServiceTakeover.STATE_INSPECTING,
        ServiceTakeover.STATE_FAILED,
    },
    ServiceTakeover.STATE_INSPECTING: {
        ServiceTakeover.STATE_PREPARING,
        ServiceTakeover.STATE_FAILED,
    },
    ServiceTakeover.STATE_PREPARING: {
        ServiceTakeover.STATE_PREPARED,
        ServiceTakeover.STATE_FAILED,
    },
    ServiceTakeover.STATE_PREPARED: {
        ServiceTakeover.STATE_ACTIVATING,
        ServiceTakeover.STATE_CANCELED,
    },
    ServiceTakeover.STATE_ACTIVATING: {
        ServiceTakeover.STATE_VERIFYING,
        ServiceTakeover.STATE_FAILED,
        ServiceTakeover.STATE_ROLLED_BACK,
        ServiceTakeover.STATE_ROLLBACK_FAILED,
    },
    ServiceTakeover.STATE_VERIFYING: {
        ServiceTakeover.STATE_SUCCEEDED,
        ServiceTakeover.STATE_FAILED,
        ServiceTakeover.STATE_ROLLED_BACK,
        ServiceTakeover.STATE_ROLLBACK_FAILED,
    },
}


@transaction.atomic
def transition_takeover(
    takeover_id,
    new_state: str,
    *,
    actor: str,
    failure_code: str = "",
    failure_message: str = "",
) -> ServiceTakeover:
    try:
        takeover = ServiceTakeover.objects.select_for_update().select_related(
            "service"
        ).get(public_id=takeover_id)
    except ServiceTakeover.DoesNotExist as exc:
        raise TakeoverError("takeover_not_found", "Takeover was not found.") from exc

    if takeover.state == new_state:
        return takeover
    if new_state not in TAKEOVER_NEXT_STATES.get(takeover.state, set()):
        raise TakeoverError(
            "invalid_takeover_transition",
            f"Illegal takeover transition: {takeover.state} -> {new_state}",
        )

    previous = takeover.state
    now = timezone.now()
    takeover.state = new_state
    if new_state in {
        ServiceTakeover.STATE_INSPECTING,
        ServiceTakeover.STATE_ACTIVATING,
    } and takeover.started_at is None:
        takeover.started_at = now
    if new_state == ServiceTakeover.STATE_PREPARED:
        takeover.prepared_at = now
    if new_state in ServiceTakeover.TERMINAL_STATES:
        takeover.completed_at = now
        takeover.failure_code = failure_code[:100]
        takeover.failure_message = failure_message[:500]
    takeover.save()

    AuditEvent.objects.create(
        event_type="service.takeover.state_changed",
        target_type="service_takeover",
        target_id=str(takeover.public_id),
        actor=actor,
        metadata={
            "service_id": str(takeover.service.public_id),
            "from_state": previous,
            "to_state": new_state,
        },
    )
    return takeover


@transaction.atomic
def queue_takeover_activation(
    *, takeover: ServiceTakeover, requested_by: str
) -> Operation:
    takeover = ServiceTakeover.objects.select_for_update().select_related(
        "service__target_server"
    ).get(pk=takeover.pk)
    if takeover.state != ServiceTakeover.STATE_PREPARED:
        raise TakeoverError(
            "takeover_not_prepared",
            "Takeover must be prepared before activation.",
        )
    if takeover.service.lifecycle_state != Service.LIFECYCLE_CONFIGURED:
        raise TakeoverError(
            "service_not_configured",
            "Service must remain configured until takeover succeeds.",
        )
    if takeover.activate_operation_id:
        raise TakeoverError(
            "takeover_already_active",
            "Takeover activation is already queued.",
        )
    operation = create_operation(
        server=takeover.service.target_server,
        kind=Operation.KIND_TAKEOVER_ACTIVATE,
        payload={"takeover_id": str(takeover.public_id)},
        actor=requested_by,
    )
    takeover.activate_operation = operation
    takeover.save(update_fields=["activate_operation", "updated_at"])
    AuditEvent.objects.create(
        event_type="service.takeover.activation_requested",
        target_type="service_takeover",
        target_id=str(takeover.public_id),
        actor=requested_by,
        metadata={
            "service_id": str(takeover.service.public_id),
            "exact_commit": takeover.requested_commit,
        },
    )
    return operation


@transaction.atomic
def cancel_prepared_takeover(
    *, takeover: ServiceTakeover, actor: str
) -> ServiceTakeover:
    takeover = ServiceTakeover.objects.select_for_update().select_related("service").get(
        pk=takeover.pk
    )
    if takeover.state != ServiceTakeover.STATE_PREPARED:
        raise TakeoverError(
            "takeover_not_prepared",
            "Only a prepared takeover can be canceled.",
        )
    if takeover.activate_operation_id:
        raise TakeoverError(
            "takeover_already_active",
            "Takeover activation has already been queued.",
        )
    canceled = transition_takeover(
        takeover.public_id,
        ServiceTakeover.STATE_CANCELED,
        actor=actor,
    )
    AuditEvent.objects.create(
        event_type="service.takeover.canceled",
        target_type="service_takeover",
        target_id=str(canceled.public_id),
        actor=actor,
        metadata={"service_id": str(canceled.service.public_id)},
    )
    return canceled


def mark_takeover_operation_started(operation: Operation) -> None:
    if operation.kind not in {
        Operation.KIND_TAKEOVER_PREPARE,
        Operation.KIND_TAKEOVER_ACTIVATE,
    }:
        return
    takeover = ServiceTakeover.objects.get(
        public_id=operation.payload["takeover_id"]
    )
    if (
        operation.kind == Operation.KIND_TAKEOVER_PREPARE
        and takeover.state == ServiceTakeover.STATE_QUEUED
    ):
        transition_takeover(
            takeover.public_id,
            ServiceTakeover.STATE_INSPECTING,
            actor=operation.actor,
        )
        return
    if (
        operation.kind == Operation.KIND_TAKEOVER_ACTIVATE
        and takeover.state == ServiceTakeover.STATE_PREPARED
    ):
        transition_takeover(
            takeover.public_id,
            ServiceTakeover.STATE_ACTIVATING,
            actor=operation.actor,
        )
        AuditEvent.objects.create(
            event_type="service.takeover.activation_started",
            target_type="service_takeover",
            target_id=str(takeover.public_id),
            actor=operation.actor,
            metadata={"service_id": str(takeover.service.public_id)},
        )


_PREPARE_SNAPSHOT_KEYS = {
    "unit_name",
    "fragment_path",
    "drop_in_paths",
    "user",
    "group",
    "working_directory",
    "exec_start_path",
    "exec_start_argv",
    "environment_file_paths",
    "restart_policy",
    "restart_delay_usec",
    "source_file_hashes",
}


def _validate_prepare_result(takeover: ServiceTakeover, result: dict) -> dict:
    import re

    if set(result) - {
        "takeover_id",
        "final_state",
        "resolved_commit",
        "source_snapshot",
        "source_fingerprint",
        "release_name",
        "release_path",
        "events",
    }:
        raise TakeoverError("invalid_takeover_result", "Unexpected prepare result field.")
    if result.get("takeover_id") != str(takeover.public_id):
        raise TakeoverError("invalid_takeover_result", "Takeover result identity mismatch.")
    if result.get("final_state") != ServiceTakeover.STATE_PREPARED:
        raise TakeoverError("invalid_takeover_result", "Prepare result did not finish prepared.")
    if result.get("resolved_commit") != takeover.requested_commit:
        raise TakeoverError("invalid_takeover_result", "Prepared commit mismatch.")
    fingerprint = result.get("source_fingerprint", "")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise TakeoverError("invalid_takeover_result", "Invalid source fingerprint.")
    release_name = result.get("release_name", "")
    if not isinstance(release_name, str) or not re.fullmatch(
        r"[0-9]{8}-[0-9]{6}-[0-9a-f]{7}(?:-[0-9]+)?", release_name
    ):
        raise TakeoverError("invalid_takeover_result", "Invalid prepared release name.")
    expected_path = (
        f"/srv/digitalafarin/apps/{takeover.service.project.slug}/"
        f"{takeover.service.name}/releases/{release_name}"
    )
    if result.get("release_path") != expected_path:
        raise TakeoverError("invalid_takeover_result", "Prepared release path mismatch.")
    snapshot = result.get("source_snapshot")
    if not isinstance(snapshot, dict) or set(snapshot) != _PREPARE_SNAPSHOT_KEYS:
        raise TakeoverError("invalid_takeover_result", "Invalid source snapshot contract.")
    if snapshot.get("unit_name") != takeover.service.unit_name:
        raise TakeoverError("invalid_takeover_result", "Source unit mismatch.")
    events = result.get("events")
    if not isinstance(events, list):
        raise TakeoverError("invalid_takeover_result", "Invalid prepare event list.")
    states = []
    for item in events:
        if not isinstance(item, dict) or set(item) - {"state", "message"}:
            raise TakeoverError("invalid_takeover_result", "Invalid prepare event.")
        states.append(item.get("state"))
    if states != [
        ServiceTakeover.STATE_INSPECTING,
        ServiceTakeover.STATE_PREPARING,
        ServiceTakeover.STATE_PREPARED,
    ]:
        raise TakeoverError("invalid_takeover_result", "Invalid prepare event sequence.")
    return {
        "resolved_commit": takeover.requested_commit,
        "source_snapshot": snapshot,
        "source_fingerprint": fingerprint,
        "release_name": release_name,
        "release_path": expected_path,
    }


def _validate_activation_result(takeover: ServiceTakeover, result: dict) -> dict:
    allowed = {
        "takeover_id",
        "final_state",
        "resolved_commit",
        "release_name",
        "previous_current_path",
        "managed_dropin_path",
        "events",
    }
    if set(result) - allowed:
        raise TakeoverError(
            "invalid_takeover_result", "Unexpected activation result field."
        )
    if result.get("takeover_id") != str(takeover.public_id):
        raise TakeoverError("invalid_takeover_result", "Takeover result identity mismatch.")
    final_state = result.get("final_state")
    if final_state not in {
        ServiceTakeover.STATE_SUCCEEDED,
        ServiceTakeover.STATE_ROLLED_BACK,
    }:
        raise TakeoverError("invalid_takeover_result", "Invalid activation final state.")
    if result.get("resolved_commit") != takeover.requested_commit:
        raise TakeoverError("invalid_takeover_result", "Activated commit mismatch.")
    if result.get("release_name") != takeover.release_name:
        raise TakeoverError("invalid_takeover_result", "Activated release mismatch.")

    expected_dropin = (
        f"/etc/systemd/system/{takeover.service.unit_name}.d/"
        "90-digitalafarin-managed.conf"
    )
    if result.get("managed_dropin_path") != expected_dropin:
        raise TakeoverError("invalid_takeover_result", "Managed drop-in path mismatch.")

    previous = result.get("previous_current_path")
    if previous is not None:
        if not isinstance(previous, str):
            raise TakeoverError("invalid_takeover_result", "Invalid previous release path.")
        release_root = PurePosixPath(
            f"/srv/digitalafarin/apps/{takeover.service.project.slug}/"
            f"{takeover.service.name}/releases"
        )
        previous_path = PurePosixPath(previous)
        if (
            not previous_path.is_absolute()
            or ".." in previous_path.parts
            or previous_path == release_root
            or not previous_path.is_relative_to(release_root)
        ):
            raise TakeoverError("invalid_takeover_result", "Invalid previous release path.")

    events = result.get("events")
    if not isinstance(events, list):
        raise TakeoverError("invalid_takeover_result", "Invalid activation event list.")
    states = []
    for item in events:
        if not isinstance(item, dict) or set(item) - {"state", "message"}:
            raise TakeoverError("invalid_takeover_result", "Invalid activation event.")
        states.append(item.get("state"))
    if states != [
        ServiceTakeover.STATE_ACTIVATING,
        ServiceTakeover.STATE_VERIFYING,
        final_state,
    ]:
        raise TakeoverError("invalid_takeover_result", "Invalid activation event sequence.")

    return {
        "final_state": final_state,
        "resolved_commit": takeover.requested_commit,
        "previous_current_path": previous,
        "managed_dropin_path": expected_dropin,
    }


def _apply_prepare_result(
    takeover: ServiceTakeover,
    operation: Operation,
    *,
    succeeded: bool,
    result: dict,
    error_code: str,
    error_message: str,
) -> ServiceTakeover:
    if not succeeded:
        if takeover.state not in ServiceTakeover.TERMINAL_STATES:
            transition_takeover(
                takeover.public_id,
                ServiceTakeover.STATE_FAILED,
                actor=operation.actor,
                failure_code=error_code or "release_prepare_failed",
                failure_message=error_message,
            )
        takeover.refresh_from_db()
        return takeover

    validated = _validate_prepare_result(takeover, result)
    if takeover.state == ServiceTakeover.STATE_PREPARED:
        current = {
            "resolved_commit": takeover.resolved_commit,
            "source_snapshot": takeover.source_snapshot,
            "source_fingerprint": takeover.source_fingerprint,
            "release_name": takeover.release_name,
            "release_path": takeover.release_path,
        }
        if current != validated:
            raise TakeoverError(
                "invalid_takeover_result",
                "Repeated prepare result does not match persisted takeover.",
            )
        return takeover
    if takeover.state == ServiceTakeover.STATE_QUEUED:
        transition_takeover(
            takeover.public_id,
            ServiceTakeover.STATE_INSPECTING,
            actor=operation.actor,
        )
    takeover.refresh_from_db()
    if takeover.state == ServiceTakeover.STATE_INSPECTING:
        transition_takeover(
            takeover.public_id,
            ServiceTakeover.STATE_PREPARING,
            actor=operation.actor,
        )
    takeover = ServiceTakeover.objects.select_for_update().select_related("service").get(
        pk=takeover.pk
    )
    if takeover.state != ServiceTakeover.STATE_PREPARING:
        raise TakeoverError(
            "invalid_takeover_transition",
            "Prepare result cannot be applied in the current state.",
        )
    for field, value in validated.items():
        setattr(takeover, field, value)
    takeover.save(
        update_fields=[
            "resolved_commit",
            "source_snapshot",
            "source_fingerprint",
            "release_name",
            "release_path",
            "updated_at",
        ]
    )
    AuditEvent.objects.create(
        event_type="service.takeover.inspected",
        target_type="service_takeover",
        target_id=str(takeover.public_id),
        actor=operation.actor,
        metadata={
            "service_id": str(takeover.service.public_id),
            "source_fingerprint": takeover.source_fingerprint,
        },
    )
    transition_takeover(
        takeover.public_id,
        ServiceTakeover.STATE_PREPARED,
        actor=operation.actor,
    )
    AuditEvent.objects.create(
        event_type="service.takeover.prepared",
        target_type="service_takeover",
        target_id=str(takeover.public_id),
        actor=operation.actor,
        metadata={
            "service_id": str(takeover.service.public_id),
            "exact_commit": takeover.resolved_commit,
            "release_name": takeover.release_name,
        },
    )
    takeover.refresh_from_db()
    return takeover


def _apply_activation_result(
    takeover: ServiceTakeover,
    operation: Operation,
    *,
    succeeded: bool,
    result: dict,
    error_code: str,
    error_message: str,
) -> ServiceTakeover:
    service = takeover.service
    if not succeeded:
        if takeover.state in ServiceTakeover.TERMINAL_STATES:
            return takeover
        target = (
            ServiceTakeover.STATE_ROLLBACK_FAILED
            if error_code == "takeover_rollback_failed"
            else ServiceTakeover.STATE_FAILED
        )
        if takeover.state == ServiceTakeover.STATE_PREPARED:
            transition_takeover(
                takeover.public_id,
                ServiceTakeover.STATE_ACTIVATING,
                actor=operation.actor,
            )
        transition_takeover(
            takeover.public_id,
            target,
            actor=operation.actor,
            failure_code=error_code or "takeover_activation_failed",
            failure_message=error_message,
        )
        if target == ServiceTakeover.STATE_ROLLBACK_FAILED:
            AuditEvent.objects.create(
                event_type="service.takeover.rollback_started",
                target_type="service_takeover",
                target_id=str(takeover.public_id),
                actor=operation.actor,
                metadata={"service_id": str(service.public_id)},
            )
        AuditEvent.objects.create(
            event_type=(
                "service.takeover.rollback_failed"
                if target == ServiceTakeover.STATE_ROLLBACK_FAILED
                else "service.takeover.failed"
            ),
            target_type="service_takeover",
            target_id=str(takeover.public_id),
            actor=operation.actor,
            metadata={
                "service_id": str(service.public_id),
                "error_code": error_code or "takeover_activation_failed",
            },
        )
        takeover.refresh_from_db()
        return takeover

    validated = _validate_activation_result(takeover, result)
    final_state = validated["final_state"]

    if takeover.state in {
        ServiceTakeover.STATE_SUCCEEDED,
        ServiceTakeover.STATE_ROLLED_BACK,
    }:
        if takeover.state != final_state:
            raise TakeoverError(
                "invalid_takeover_result",
                "Repeated activation result does not match persisted takeover.",
            )
        if takeover.previous_current_path != validated["previous_current_path"]:
            raise TakeoverError(
                "invalid_takeover_result",
                "Repeated activation previous release does not match persisted takeover.",
            )
        if takeover.managed_dropin_path != validated["managed_dropin_path"]:
            raise TakeoverError(
                "invalid_takeover_result",
                "Repeated activation drop-in does not match persisted takeover.",
            )
        if final_state == ServiceTakeover.STATE_SUCCEEDED:
            release = Release.objects.filter(takeover=takeover).first()
            if (
                release is None
                or release.service_id != service.id
                or release.name != takeover.release_name
                or release.exact_commit != takeover.requested_commit
                or release.path != takeover.release_path
                or release.activated_at is None
                or service.lifecycle_state != Service.LIFECYCLE_MANAGED
            ):
                raise TakeoverError(
                    "invalid_takeover_result",
                    "Persisted successful takeover is incomplete.",
                )
        return takeover

    if takeover.state == ServiceTakeover.STATE_PREPARED:
        transition_takeover(
            takeover.public_id,
            ServiceTakeover.STATE_ACTIVATING,
            actor=operation.actor,
        )
    takeover.refresh_from_db()
    if takeover.state != ServiceTakeover.STATE_ACTIVATING:
        raise TakeoverError(
            "invalid_takeover_transition",
            "Activation result cannot be applied in the current state.",
        )

    takeover.previous_current_path = validated["previous_current_path"]
    takeover.managed_dropin_path = validated["managed_dropin_path"]
    takeover.resolved_commit = validated["resolved_commit"]
    takeover.save(
        update_fields=[
            "previous_current_path",
            "managed_dropin_path",
            "resolved_commit",
            "updated_at",
        ]
    )
    transition_takeover(
        takeover.public_id,
        ServiceTakeover.STATE_VERIFYING,
        actor=operation.actor,
    )

    if final_state == ServiceTakeover.STATE_ROLLED_BACK:
        AuditEvent.objects.create(
            event_type="service.takeover.rollback_started",
            target_type="service_takeover",
            target_id=str(takeover.public_id),
            actor=operation.actor,
            metadata={"service_id": str(service.public_id)},
        )
        transition_takeover(
            takeover.public_id,
            ServiceTakeover.STATE_ROLLED_BACK,
            actor=operation.actor,
        )
        AuditEvent.objects.create(
            event_type="service.takeover.rolled_back",
            target_type="service_takeover",
            target_id=str(takeover.public_id),
            actor=operation.actor,
            metadata={"service_id": str(service.public_id)},
        )
        takeover.refresh_from_db()
        return takeover

    AuditEvent.objects.create(
        event_type="service.takeover.health_passed",
        target_type="service_takeover",
        target_id=str(takeover.public_id),
        actor=operation.actor,
        metadata={
            "service_id": str(service.public_id),
            "health_port": service.service_port,
        },
    )
    release, created = Release.objects.get_or_create(
        takeover=takeover,
        defaults={
            "service": service,
            "name": takeover.release_name,
            "exact_commit": takeover.requested_commit,
            "path": takeover.release_path,
            "activated_at": timezone.now(),
        },
    )
    if not created:
        if (
            release.service_id != service.id
            or release.name != takeover.release_name
            or release.exact_commit != takeover.requested_commit
            or release.path != takeover.release_path
        ):
            raise TakeoverError(
                "invalid_takeover_result",
                "Existing takeover release does not match activation result.",
            )
        if release.activated_at is None:
            release.activated_at = timezone.now()
            release.save(update_fields=["activated_at"])

    service.lifecycle_state = Service.LIFECYCLE_MANAGED
    service.save(update_fields=["lifecycle_state", "updated_at"])
    transition_takeover(
        takeover.public_id,
        ServiceTakeover.STATE_SUCCEEDED,
        actor=operation.actor,
    )
    AuditEvent.objects.create(
        event_type="service.takeover.succeeded",
        target_type="service_takeover",
        target_id=str(takeover.public_id),
        actor=operation.actor,
        metadata={
            "service_id": str(service.public_id),
            "unit_name": service.unit_name,
            "exact_commit": takeover.requested_commit,
            "release_name": takeover.release_name,
            "source_fingerprint": takeover.source_fingerprint,
            "managed_working_directory": (
                f"/srv/digitalafarin/apps/{service.project.slug}/"
                f"{service.name}/current/{service.root_directory}"
            ),
            "health_port": service.service_port,
        },
    )
    takeover.refresh_from_db()
    return takeover


@transaction.atomic
def apply_takeover_result(
    operation: Operation,
    *,
    succeeded: bool,
    result: dict,
    error_code: str = "",
    error_message: str = "",
) -> ServiceTakeover:
    if operation.kind not in {
        Operation.KIND_TAKEOVER_PREPARE,
        Operation.KIND_TAKEOVER_ACTIVATE,
    }:
        raise TakeoverError("invalid_takeover_operation", "Unsupported takeover operation.")
    try:
        takeover = ServiceTakeover.objects.select_for_update().select_related(
            "service__project"
        ).get(
            public_id=operation.payload["takeover_id"],
            service__target_server=operation.server,
        )
    except (KeyError, ServiceTakeover.DoesNotExist) as exc:
        raise TakeoverError("takeover_not_found", "Takeover was not found.") from exc

    if operation.kind == Operation.KIND_TAKEOVER_PREPARE:
        return _apply_prepare_result(
            takeover,
            operation,
            succeeded=succeeded,
            result=result,
            error_code=error_code,
            error_message=error_message,
        )
    return _apply_activation_result(
        takeover,
        operation,
        succeeded=succeeded,
        result=result,
        error_code=error_code,
        error_message=error_message,
    )
