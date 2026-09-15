from django.db import transaction
from django.utils import timezone

from control.models import AuditEvent, Deployment, DeploymentEvent


class DeploymentTransitionError(RuntimeError):
    pass


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
