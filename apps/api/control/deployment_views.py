from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.deployment_serializers import (
    AdoptServiceSerializer,
    DeploymentConfigurationSerializer,
    ProjectSerializer,
    ServiceSerializer,
    ServiceSettingsSerializer,
)
from control.models import AuditEvent, Deployment, Operation, Project, Server, Service
from control.permissions import require_scope
from control.operation_serializers import is_protected_unit
from control.services.operations import create_operation
from control.services.service_adoption import (
    ServiceAdoptionError,
    adopt_existing_service,
    configure_service_deployment,
)
from control.services.deployments import DeploymentAdmissionError, queue_deployment, queue_rollback
from control.environment_views import EnvironmentVariableSerializer
from control.volume_views import serialize_volume
from control.database_views import serialize_database
from control.domain_views import serialize_domain


class ProjectListCreateView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]

    def get_permissions(self):
        scope = "operations:create" if self.request.method == "POST" else "operations:read"
        return [require_scope(scope)()]

    def get(self, request):
        return Response({"items": ProjectSerializer(Project.objects.all(), many=True).data})

    def post(self, request):
        serializer = ProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        AuditEvent.objects.create(
            event_type="project.created",
            target_type="project",
            target_id=str(project.public_id),
            actor=request.user.name,
            metadata={"slug": project.slug},
        )
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class ProjectServiceListCreateView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]

    def get_permissions(self):
        scope = "operations:create" if self.request.method == "POST" else "operations:read"
        return [require_scope(scope)()]

    def _project(self, project_id):
        try:
            return Project.objects.get(public_id=project_id)
        except Project.DoesNotExist:
            return None

    def get(self, request, project_id):
        project = self._project(project_id)
        if project is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(
            {"items": ServiceSerializer(project.services.all(), many=True).data}
        )

    def post(self, request, project_id):
        project = self._project(project_id)
        if project is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = ServiceSerializer(data=request.data, context={"project": project})
        serializer.is_valid(raise_exception=True)
        service = serializer.save()
        return Response(
            ServiceSerializer(service).data, status=status.HTTP_201_CREATED
        )


class ProjectServiceAdoptView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def post(self, request, project_id):
        try:
            project = Project.objects.get(public_id=project_id)
        except Project.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = AdoptServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            server = Server.objects.get(
                public_id=serializer.validated_data["server_id"],
                is_active=True,
            )
        except Server.DoesNotExist:
            return Response(
                {"error": "server_not_found", "message": "Server not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            service = adopt_existing_service(
                project=project,
                server=server,
                unit_name=serializer.validated_data["unit_name"],
                name=serializer.validated_data["name"],
                actor=request.user.name,
            )
        except ServiceAdoptionError as exc:
            http_status = (
                status.HTTP_404_NOT_FOUND
                if exc.code == "inventory_unit_not_found"
                else status.HTTP_409_CONFLICT
            )
            return Response(
                {"error": exc.code, "message": str(exc)}, status=http_status
            )
        return Response(ServiceSerializer(service).data, status=status.HTTP_201_CREATED)


class ServiceDeploymentConfigurationView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def put(self, request, service_id):
        try:
            service = Service.objects.select_related("project", "target_server").get(
                public_id=service_id
            )
        except Service.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = DeploymentConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            service = configure_service_deployment(
                service=service,
                configuration=serializer.validated_data,
                actor=request.user.name,
            )
        except ServiceAdoptionError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(ServiceSerializer(service).data)


class ProjectDetailView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]

    def get_permissions(self):
        scope = "operations:read" if self.request.method == "GET" else "operations:create"
        return [require_scope(scope)()]

    def _project(self, project_id):
        try:
            return Project.objects.get(public_id=project_id)
        except Project.DoesNotExist:
            return None

    def get(self, request, project_id):
        project = self._project(project_id)
        if project is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        data = ProjectSerializer(project).data
        data.update(
            services=ServiceSerializer(project.services.all(), many=True).data,
            variables=EnvironmentVariableSerializer(project.environment_variables.all(), many=True).data,
            volumes=[serialize_volume(item) for item in project.volumes.all()],
            databases=[serialize_database(item) for item in project.databases.all()],
            domains=[serialize_domain(item) for item in project.domains.all()],
        )
        return Response(data)

    def patch(self, request, project_id):
        project = self._project(project_id)
        if project is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = ProjectSerializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        requested_slug = serializer.validated_data.get("slug", project.slug)
        if requested_slug != project.slug and project.services.exists():
            return Response(
                {
                    "error": "project_slug_locked",
                    "message": "Project slug cannot change while services are attached.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        project = serializer.save()
        AuditEvent.objects.create(
            event_type="project.updated",
            target_type="project",
            target_id=str(project.public_id),
            actor=request.user.name,
            metadata={"slug": project.slug},
        )
        return Response(ProjectSerializer(project).data)

    def delete(self, request, project_id):
        project = self._project(project_id)
        if project is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        blockers = {
            "services": project.services.count(),
            "variables": project.environment_variables.count(),
            "volumes": project.volumes.count(),
            "databases": project.databases.count(),
            "domains": project.domains.count(),
        }
        blockers = {key: value for key, value in blockers.items() if value}
        if blockers:
            return Response(
                {
                    "error": "project_not_empty",
                    "message": "Project cannot be deleted while managed resources are attached.",
                    "blockers": blockers,
                },
                status=status.HTTP_409_CONFLICT,
            )
        project_id_value = str(project.public_id)
        project_slug = project.slug
        with transaction.atomic():
            project.delete()
            AuditEvent.objects.create(
                event_type="project.deleted",
                target_type="project",
                target_id=project_id_value,
                actor=request.user.name,
                metadata={"slug": project_slug},
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ServiceSettingsDetailView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def _service(self, service_id):
        try:
            return Service.objects.select_related("project", "target_server").get(
                public_id=service_id
            )
        except Service.DoesNotExist:
            return None

    def patch(self, request, service_id):
        service = self._service(service_id)
        if service is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if is_protected_unit(service.unit_name):
            return Response(
                {"error": "protected_service", "message": "Protected services cannot be edited through generic settings."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = ServiceSettingsSerializer(service, data=request.data)
        serializer.is_valid(raise_exception=True)
        service = serializer.save()
        AuditEvent.objects.create(
            event_type="service.updated",
            target_type="service",
            target_id=str(service.public_id),
            actor=request.user.name,
            metadata={"project_id": str(service.project.public_id), "unit_name": service.unit_name},
        )
        return Response(ServiceSerializer(service).data)

    def delete(self, request, service_id):
        service = self._service(service_id)
        if service is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if is_protected_unit(service.unit_name):
            return Response(
                {"error": "protected_service", "message": "Protected services cannot be removed from Platform management."},
                status=status.HTTP_409_CONFLICT,
            )
        blockers = {
            "health_check": int(hasattr(service, "health_check")),
            "deployments": service.deployments.count(),
            "releases": service.releases.count(),
            "takeovers": service.takeovers.count(),
            "variables": service.environment_variables.count(),
            "volumes": service.volumes.count(),
            "databases": service.databases.count(),
            "domains": service.domains.count(),
            "github_deliveries": service.github_deliveries.count(),
        }
        blockers = {key: value for key, value in blockers.items() if value}
        if blockers:
            return Response(
                {
                    "error": "service_has_dependencies",
                    "message": "Service cannot be removed while Platform resources or history are attached.",
                    "blockers": blockers,
                },
                status=status.HTTP_409_CONFLICT,
            )
        service_id_value = str(service.public_id)
        project_id_value = str(service.project.public_id)
        unit_name = service.unit_name
        with transaction.atomic():
            service.delete()
            AuditEvent.objects.create(
                event_type="service.removed",
                target_type="service",
                target_id=service_id_value,
                actor=request.user.name,
                metadata={
                    "project_id": project_id_value,
                    "unit_name": unit_name,
                    "host_mutated": False,
                },
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ServiceManagedDeleteView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def post(self, request, service_id):
        if request.data:
            return Response({"error": "invalid_request"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            service = Service.objects.select_related("project", "target_server").get(public_id=service_id)
        except Service.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if is_protected_unit(service.unit_name):
            return Response(
                {"error": "protected_service", "message": "Protected services cannot be deleted."},
                status=status.HTTP_409_CONFLICT,
            )
        if service.lifecycle_state != Service.LIFECYCLE_MANAGED:
            return Response(
                {"error": "service_not_managed", "message": "Only managed services can use host cleanup."},
                status=status.HTTP_409_CONFLICT,
            )
        blockers = {
            "volumes": service.volumes.count(),
            "databases": service.databases.count(),
            "domains": service.domains.count(),
        }
        blockers = {key: value for key, value in blockers.items() if value}
        if blockers:
            return Response(
                {"error": "persistent_resources_attached", "message": "Remove persistent resources before deleting this service.", "blockers": blockers},
                status=status.HTTP_409_CONFLICT,
            )
        if service.target_server.status != "online":
            return Response({"error": "server_offline"}, status=status.HTTP_409_CONFLICT)
        active = service.target_server.operations.filter(
            kind=Operation.KIND_SERVICE_DELETE,
            state__in=[Operation.STATE_QUEUED, Operation.STATE_CLAIMED, Operation.STATE_RUNNING],
            payload__service_id=str(service.public_id),
        ).first()
        if active:
            return Response(
                {"id": str(active.public_id), "kind": active.kind, "state": active.state},
                status=status.HTTP_200_OK,
            )
        operation = create_operation(
            server=service.target_server,
            kind=Operation.KIND_SERVICE_DELETE,
            payload={"service_id": str(service.public_id)},
            actor=request.user.name,
        )
        AuditEvent.objects.create(
            event_type="service.delete_requested",
            target_type="service",
            target_id=str(service.public_id),
            actor=request.user.name,
            metadata={"unit_name": service.unit_name},
        )
        return Response(
            {"id": str(operation.public_id), "kind": operation.kind, "state": operation.state},
            status=status.HTTP_202_ACCEPTED,
        )


class ServerBootstrapView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def post(self, request, server_id):
        if request.data:
            return Response(
                {"error": "invalid_request", "message": "Bootstrap accepts no caller configuration."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            server = Server.objects.get(public_id=server_id, is_active=True)
        except Server.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if server.status != "online":
            return Response(
                {"error": "server_offline", "message": "Server is not online."},
                status=status.HTTP_409_CONFLICT,
            )
        operation = create_operation(
            server=server,
            kind=Operation.KIND_SERVER_BOOTSTRAP,
            payload={},
            actor=request.user.name,
        )
        return Response(
            {"id": str(operation.public_id), "kind": operation.kind, "state": operation.state},
            status=status.HTTP_201_CREATED,
        )


def serialize_deployment(deployment, operation=None):
    data = {
        "id": str(deployment.public_id),
        "service_id": str(deployment.service.public_id),
        "requested_ref": deployment.requested_ref,
        "resolved_commit": deployment.resolved_commit,
        "state": deployment.state,
        "requested_by": deployment.requested_by,
        "queued_at": deployment.queued_at,
        "started_at": deployment.started_at,
        "completed_at": deployment.completed_at,
    }
    if operation:
        data["operation_id"] = str(operation.public_id)
        data["operation"] = {
            "id": str(operation.public_id),
            "state": operation.state,
            "error_code": operation.error_code,
            "error_message": operation.error_message,
            "created_at": operation.created_at,
            "claimed_at": operation.claimed_at,
            "started_at": operation.started_at,
            "completed_at": operation.completed_at,
        }
    return data


class ServiceDeploymentListCreateView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]

    def get_permissions(self):
        scope = "operations:create" if self.request.method == "POST" else "operations:read"
        return [require_scope(scope)()]

    def get(self, request, service_id):
        try:
            service = Service.objects.get(public_id=service_id)
        except Service.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({"items": [serialize_deployment(item) for item in service.deployments.all()]})

    def post(self, request, service_id):
        if set(request.data) - {"commit"}:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        try:
            service = Service.objects.get(public_id=service_id)
        except Service.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        commit = request.data.get("commit", "")
        if commit and (len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit)):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        try:
            deployment, operation = queue_deployment(
                service=service,
                requested_ref=commit or service.branch,
                resolved_commit=commit,
                requested_by=request.user.name,
            )
        except DeploymentAdmissionError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(serialize_deployment(deployment, operation), status=status.HTTP_201_CREATED)


class DeploymentRedeployView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def post(self, request, deployment_id):
        if request.data:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        try:
            source = Deployment.objects.select_related("service__target_server").get(public_id=deployment_id)
        except Deployment.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not source.resolved_commit:
            return Response(status=status.HTTP_409_CONFLICT)
        try:
            deployment, operation = queue_deployment(
                service=source.service,
                requested_ref=source.resolved_commit,
                resolved_commit=source.resolved_commit,
                requested_by=request.user.name,
                source=source,
            )
        except DeploymentAdmissionError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(serialize_deployment(deployment, operation), status=status.HTTP_201_CREATED)


class DeploymentRollbackView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def post(self, request, deployment_id):
        if request.data:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        try:
            source = Deployment.objects.select_related("service__target_server", "active_release", "previous_release").get(public_id=deployment_id)
        except Deployment.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        release = source.previous_release or source.active_release
        if release is None:
            return Response(status=status.HTTP_409_CONFLICT)
        try:
            deployment, operation = queue_rollback(
                source=source, release=release, requested_by=request.user.name
            )
        except DeploymentAdmissionError as exc:
            return Response(
                {"error": exc.code, "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(serialize_deployment(deployment, operation), status=status.HTTP_201_CREATED)


class DeploymentDetailView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:read")]

    def get(self, request, deployment_id):
        try:
            deployment = Deployment.objects.select_related("service", "active_release", "previous_release").get(public_id=deployment_id)
        except Deployment.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        operation = (
            Operation.objects.filter(
                server=deployment.service.target_server,
                kind__in=[
                    Operation.KIND_DEPLOYMENT_DEPLOY,
                    Operation.KIND_DEPLOYMENT_ROLLBACK,
                ],
                payload__deployment_id=str(deployment.public_id),
            )
            .order_by("-created_at")
            .first()
        )
        data = serialize_deployment(deployment, operation)
        data["active_release"] = deployment.active_release.name if deployment.active_release else None
        data["previous_release"] = deployment.previous_release.name if deployment.previous_release else None
        data["events"] = [
            {"id": str(item.public_id), "state": item.state, "message": item.message, "metadata": item.metadata, "created_at": item.created_at}
            for item in deployment.events.all()
        ]
        return Response(data)
