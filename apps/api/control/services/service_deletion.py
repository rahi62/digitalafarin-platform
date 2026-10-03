from django.db import transaction

from control.models import AuditEvent, Service


def finalize_service_deletion(service_id: str, *, actor: str) -> None:
    with transaction.atomic():
        service = Service.objects.select_for_update().select_related("project").get(public_id=service_id)
        identity = {
            "project_id": str(service.project.public_id),
            "project_slug": service.project.slug,
            "service_name": service.name,
            "unit_name": service.unit_name,
            "host_mutated": True,
        }
        # Releases protect their provenance records, so remove release metadata first.
        service.releases.all().delete()
        service.deployments.all().delete()
        service.takeovers.all().delete()
        service.github_deliveries.all().delete()
        service.environment_variables.all().delete()
        if hasattr(service, "health_check"):
            service.health_check.delete()
        target_id = str(service.public_id)
        service.delete()
        AuditEvent.objects.create(
            event_type="service.deleted",
            target_type="service",
            target_id=target_id,
            actor=actor,
            metadata=identity,
        )
