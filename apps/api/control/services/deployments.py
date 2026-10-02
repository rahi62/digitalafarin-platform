from django.db import transaction
from django.utils import timezone

from control.models import AuditEvent, Deployment, DeploymentEvent, Operation, Release
from control.services.operations import create_operation


class DeploymentTransitionError(RuntimeError):
    pass


class DeploymentAdmissionError(RuntimeError):
    def __init__(self, message: str, code: str = "deployment_blocked"):
        super().__init__(message)
        self.code = code


def require_managed_service(service):
    if service.lifecycle_state != service.LIFECYCLE_MANAGED:
        raise DeploymentAdmissionError(
            "Service has not completed controlled takeover.",
            code="service_not_managed",
        )


def deployment_admission(server) -> dict[str, bool]:
    if server.status != "online":
        raise DeploymentAdmissionError("fresh disk telemetry is required")
    if server.disk_percent >= 90:
        raise DeploymentAdmissionError("disk usage blocks deployment")
    return {"allowed": True, "warning": server.disk_percent >= 80}


NEXT_STATES = {
    "queued": {"preparing", "failed"},
    "preparing": {"cloning", "failed"},
    "cloning": {"building", "failed"},
    "building": {"releasing", "failed"},
    "releasing": {"health_check", "failed"},
    "health_check": {"activating", "failed"},
    "activating": {"verifying", "failed", "rolled_back"},
    "verifying": {"succeeded", "failed", "rolled_back"},
    "succeeded": set(),
    "failed": set(),
    "rolled_back": set(),
}


@transaction.atomic
def queue_deployment(
    *, service, requested_ref: str, requested_by: str, resolved_commit: str = "", source=None
):
    require_managed_service(service)
    admission = deployment_admission(service.target_server)
    deployment = Deployment.objects.create(
        service=service,
        requested_ref=requested_ref,
        resolved_commit=resolved_commit,
        requested_by=requested_by,
        source_deployment=source,
    )
    DeploymentEvent.objects.create(
        deployment=deployment,
        state="queued",
        message="Deployment queued",
        metadata={"disk_warning": admission["warning"]},
    )
    AuditEvent.objects.create(
        event_type="deployment.queued",
        target_type="deployment",
        target_id=str(deployment.public_id),
        actor=requested_by,
        metadata={"service_id": str(service.public_id), "disk_warning": admission["warning"]},
    )
    operation = create_operation(
        server=service.target_server,
        kind=Operation.KIND_DEPLOYMENT_DEPLOY,
        payload={"deployment_id": str(deployment.public_id)},
        actor=requested_by,
    )
    return deployment, operation


@transaction.atomic
def queue_rollback(*, source: Deployment, release, requested_by: str):
    require_managed_service(source.service)
    deployment = Deployment.objects.create(
        service=source.service,
        requested_ref=release.exact_commit,
        resolved_commit=release.exact_commit,
        requested_by=requested_by,
        source_deployment=source,
    )
    DeploymentEvent.objects.create(
        deployment=deployment,
        state="queued",
        message="Rollback queued",
        metadata={"release_id": str(release.public_id)},
    )
    operation = create_operation(
        server=source.service.target_server,
        kind=Operation.KIND_DEPLOYMENT_ROLLBACK,
        payload={"deployment_id": str(deployment.public_id), "release_id": str(release.public_id)},
        actor=requested_by,
    )
    return deployment, operation


@transaction.atomic
def transition_deployment(
    deployment_id,
    new_state: str,
    *,
    message: str = "",
    metadata: dict | None = None,
    failure_code: str = "",
) -> Deployment:
    try:
        deployment = Deployment.objects.select_for_update().select_related("service").get(
            public_id=deployment_id
        )
    except Deployment.DoesNotExist as exc:
        raise DeploymentTransitionError("deployment not found") from exc
    previous = deployment.state
    if new_state not in NEXT_STATES.get(previous, set()):
        raise DeploymentTransitionError(f"illegal deployment transition: {previous} -> {new_state}")
    now = timezone.now()
    deployment.state = new_state
    if new_state == "preparing" and deployment.started_at is None:
        deployment.started_at = now
    if new_state in {"succeeded", "failed", "rolled_back"}:
        deployment.completed_at = now
        deployment.failure_code = failure_code[:100]
    deployment.save(
        update_fields=["state", "started_at", "completed_at", "failure_code"]
    )
    safe_metadata = metadata or {}
    event = DeploymentEvent.objects.create(
        deployment=deployment,
        state=new_state,
        message=message[:500],
        metadata=safe_metadata,
    )
    AuditEvent.objects.create(
        event_type="deployment.transition",
        target_type="deployment",
        target_id=str(deployment.public_id),
        actor=deployment.requested_by,
        metadata={
            "from_state": previous,
            "to_state": new_state,
            "service_id": str(deployment.service.public_id),
            "event_id": str(event.public_id),
        },
    )
    return deployment


@transaction.atomic
def apply_deployment_result(operation: Operation, *, succeeded: bool, result: dict, error_code: str = "") -> Deployment:
    deployment = Deployment.objects.select_for_update().select_related("service__project").get(
        public_id=operation.payload["deployment_id"], service__target_server=operation.server
    )
    if not succeeded:
        if deployment.state not in {"succeeded", "failed", "rolled_back"}:
            transition_deployment(deployment.public_id, "failed", failure_code=error_code or "deployment_failed")
        deployment.refresh_from_db()
        return deployment
    events = result.get("events")
    final_state = result.get("final_state")
    if not isinstance(events, list) or final_state not in {"succeeded", "rolled_back"}:
        raise DeploymentTransitionError("invalid deployment result")
    for item in events:
        if not isinstance(item, dict) or set(item) - {"state", "message"}:
            raise DeploymentTransitionError("invalid deployment event")
        transition_deployment(
            deployment.public_id,
            item.get("state", ""),
            message=str(item.get("message", ""))[:500],
            failure_code="health_failed" if item.get("state") == "rolled_back" else "",
        )
    deployment.refresh_from_db()
    exact_commit = result.get("exact_commit", "")
    release_name = result.get("release_name", "")
    if len(exact_commit) != 40 or not release_name:
        raise DeploymentTransitionError("invalid release result")
    service = deployment.service
    release, _created = service.releases.get_or_create(
        name=release_name,
        defaults={
            "deployment": deployment,
            "exact_commit": exact_commit,
            "path": f"/srv/digitalafarin/apps/{service.project.slug}/{service.name}/releases/{release_name}",
        },
    )
    if release.exact_commit != exact_commit:
        raise DeploymentTransitionError('release commit mismatch')
    deployment.resolved_commit = exact_commit
    if final_state == "succeeded":
        previous = (
            Release.objects.filter(service=service, activated_at__isnull=False)
            .exclude(pk=release.pk)
            .order_by("-activated_at")
            .first()
        )
        release.activated_at = timezone.now()
        release.save(update_fields=["activated_at"])
        deployment.active_release = release
        deployment.previous_release = previous
    deployment.save(
        update_fields=["resolved_commit", "active_release", "previous_release"]
    )
    return deployment
