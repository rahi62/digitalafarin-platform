from urllib.parse import quote

from django.core.exceptions import ObjectDoesNotExist

import os

from control.models import DatabaseResource, Deployment, Domain, Operation, Release, ServiceTakeover
from control.services.secrets import decrypt_secret
from control.services.variables import resolve_environment


def build_health_check_context(service) -> dict:
    try:
        check = service.health_check
    except ObjectDoesNotExist:
        return {
            "url": f"http://127.0.0.1:{service.service_port}/",
            "expected_status": 200,
            "attempts": 6,
            "timeout_seconds": 10,
            "interval_seconds": 5,
        }
    return {
        "url": f"http://127.0.0.1:{service.service_port}{check.path}",
        "expected_status": check.expected_status,
        "attempts": check.attempts,
        "timeout_seconds": check.timeout_seconds,
        "interval_seconds": check.interval_seconds,
    }


def _deployment_environment(service) -> dict[str, str]:
    environment = resolve_environment(service, "production", include_secrets=True)
    database = DatabaseResource.objects.filter(service=service).first()
    if database:
        password = quote(decrypt_secret(database.password_ciphertext), safe="")
        environment["DATABASE_URL"] = (
            f"postgresql://{database.username}:{password}@127.0.0.1/{database.database_name}"
        )
    return environment


def build_execution_context(operation: Operation) -> dict | None:
    if operation.kind == Operation.KIND_SERVICE_DELETE:
        from control.models import Service
        service = Service.objects.select_related("project").get(
            public_id=operation.payload["service_id"], target_server=operation.server
        )
        return {
            "service_id": str(service.public_id),
            "project_slug": service.project.slug,
            "service_name": service.name,
            "unit_name": service.unit_name,
            "root_directory": service.root_directory or ".",
        }
    if operation.kind in {Operation.KIND_DOMAIN_CONFIGURE, Operation.KIND_DOMAIN_SSL}:
        domain = Domain.objects.select_related("service").get(
            public_id=operation.payload["domain_id"], server=operation.server
        )
        context = {"hostname": domain.hostname, "service_port": domain.service.service_port}
        if operation.kind == Operation.KIND_DOMAIN_SSL:
            context = {"hostname": domain.hostname, "email": os.getenv("PLATFORM_CERTBOT_EMAIL", "")}
        return context
    if operation.kind in {Operation.KIND_DATABASE_CREATE, Operation.KIND_DATABASE_RESTORE}:
        database = DatabaseResource.objects.get(
            public_id=operation.payload["database_resource_id"], server=operation.server
        )
        context = {"database_name": database.database_name, "username": database.username}
        if operation.kind == Operation.KIND_DATABASE_CREATE:
            context["password"] = decrypt_secret(database.password_ciphertext)
        else:
            context["backup_name"] = operation.payload["backup_name"]
        return context
    if operation.kind == Operation.KIND_DEPLOYMENT_DEPLOY:
        deployment = Deployment.objects.select_related("service__project").get(
            public_id=operation.payload["deployment_id"], service__target_server=operation.server
        )
        service = deployment.service
        context = {
            "deployment_id": str(deployment.public_id),
            "project_slug": service.project.slug,
            "service_name": service.name,
            "repository": service.repository,
            "requested_ref": deployment.requested_ref,
            "exact_commit": deployment.resolved_commit,
            "runtime": service.runtime,
            "install_configuration": service.install_configuration,
            "build_configuration": service.build_configuration,
            "root_directory": service.root_directory,
            "unit_name": service.unit_name,
            "environment": _deployment_environment(service),
            "volumes": [
                {"host_path": item.host_path, "mount_path": item.mount_path}
                for item in service.volumes.all()
            ],
            "health_check": build_health_check_context(service),
        }
        if (
            service.project.slug == "digitalafarin-platform"
            and service.name == "platform-web"
            and service.unit_name == "digitalafarin-platform-web.service"
        ):
            # The privileged helper binds this exact service to its trusted local repo.
            # GitHub App source download is unnecessary for the Platform's own Web release.
            context["source_transport"] = "trusted_local"
        return context
    if operation.kind == Operation.KIND_TAKEOVER_PREPARE:
        takeover = ServiceTakeover.objects.select_related(
            "service__project", "service__target_server"
        ).get(
            public_id=operation.payload["takeover_id"],
            service__target_server=operation.server,
        )
        service = takeover.service
        context = {
            "takeover_id": str(takeover.public_id),
            "service_id": str(service.public_id),
            "project_slug": service.project.slug,
            "service_name": service.name,
            "unit_name": service.unit_name,
            "repository": service.repository,
            "exact_commit": takeover.requested_commit,
            "runtime": service.runtime,
            "root_directory": service.root_directory,
            "install_configuration": service.install_configuration,
            "build_configuration": service.build_configuration,
            "service_port": service.service_port,
            "health_check": takeover.health_check_snapshot,
        }
        if (
            service.project.slug == "digitalafarin-platform"
            and service.name == "platform-web"
            and service.unit_name == "digitalafarin-platform-web.service"
        ):
            context["source_transport"] = "trusted_local"
        return context
    if operation.kind == Operation.KIND_TAKEOVER_ACTIVATE:
        takeover = ServiceTakeover.objects.select_related(
            "service__project", "service__target_server"
        ).get(
            public_id=operation.payload["takeover_id"],
            service__target_server=operation.server,
        )
        service = takeover.service
        expected_release_path = (
            f"/srv/digitalafarin/apps/{service.project.slug}/"
            f"{service.name}/releases/{takeover.release_name}"
        )
        return {
            "takeover_id": str(takeover.public_id),
            "service_id": str(service.public_id),
            "project_slug": service.project.slug,
            "service_name": service.name,
            "unit_name": service.unit_name,
            "exact_commit": takeover.requested_commit,
            "root_directory": service.root_directory,
            "source_fingerprint": takeover.source_fingerprint,
            "release_name": takeover.release_name,
            "release_path": expected_release_path,
            "health_check": takeover.health_check_snapshot,
        }
    if operation.kind == Operation.KIND_DEPLOYMENT_ROLLBACK:
        deployment = Deployment.objects.select_related("service__project").get(
            public_id=operation.payload["deployment_id"], service__target_server=operation.server
        )
        release = Release.objects.get(
            public_id=operation.payload["release_id"], service=deployment.service
        )
        service = deployment.service
        return {
            "deployment_id": str(deployment.public_id),
            "service_root": f"/srv/digitalafarin/apps/{service.project.slug}/{service.name}",
            "release_path": release.path,
            "exact_commit": release.exact_commit,
            "unit_name": service.unit_name,
            "health_check": build_health_check_context(service),
        }
    return None
