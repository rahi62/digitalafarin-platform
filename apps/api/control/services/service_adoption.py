from django.db import IntegrityError, transaction

from control.models import AuditEvent, Service, ServiceSnapshot


class ServiceAdoptionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@transaction.atomic
def adopt_existing_service(
    *, project, server, unit_name: str, name: str, actor: str
) -> Service:
    if not ServiceSnapshot.objects.filter(server=server, unit_name=unit_name).exists():
        raise ServiceAdoptionError(
            "inventory_unit_not_found", "Inventory unit was not found."
        )
    if Service.objects.filter(target_server=server, unit_name=unit_name).exists():
        raise ServiceAdoptionError(
            "unit_already_adopted", "Service unit is already adopted."
        )
    if Service.objects.filter(project=project, name=name).exists():
        raise ServiceAdoptionError(
            "service_name_in_use", "Project service name is already in use."
        )
    try:
        service = Service.objects.create(
            project=project,
            name=name,
            executor=Service.EXECUTOR_SYSTEMD,
            unit_name=unit_name,
            lifecycle_state=Service.LIFECYCLE_ADOPTED,
            target_server=server,
        )
    except IntegrityError as exc:
        raise ServiceAdoptionError(
            "adoption_conflict",
            "Service adoption conflicts with an existing binding.",
        ) from exc
    AuditEvent.objects.create(
        event_type="service.adopted",
        target_type="service",
        target_id=str(service.public_id),
        actor=actor,
        metadata={
            "project_id": str(project.public_id),
            "server_id": str(server.public_id),
            "unit_name": unit_name,
            "service_name": name,
        },
    )
    return service


@transaction.atomic
def configure_service_deployment(
    *, service: Service, configuration: dict, actor: str
) -> Service:
    if service.lifecycle_state not in {
        Service.LIFECYCLE_ADOPTED,
        Service.LIFECYCLE_CONFIGURED,
    }:
        raise ServiceAdoptionError(
            "invalid_service_lifecycle",
            "Managed services cannot be configured through the Stage B2 endpoint.",
        )
    fields = [
        "repository",
        "branch",
        "root_directory",
        "runtime",
        "install_configuration",
        "build_configuration",
        "service_port",
    ]
    for field in fields:
        setattr(service, field, configuration[field])
    service.lifecycle_state = Service.LIFECYCLE_CONFIGURED
    service.save(update_fields=[*fields, "lifecycle_state", "updated_at"])
    AuditEvent.objects.create(
        event_type="service.deployment_configured",
        target_type="service",
        target_id=str(service.public_id),
        actor=actor,
        metadata={
            "project_id": str(service.project.public_id),
            "server_id": str(service.target_server.public_id),
            "unit_name": service.unit_name,
            "service_name": service.name,
            "fields": fields,
        },
    )
    return service
