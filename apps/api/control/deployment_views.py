from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.deployment_serializers import ProjectSerializer, ServiceSerializer
from control.models import Deployment, Operation, Project, Server, Service
from control.permissions import require_scope
from control.services.operations import create_operation
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


class ProjectDetailView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:read")]

    def get(self, request, project_id):
        try:
            project = Project.objects.get(public_id=project_id)
        except Project.DoesNotExist:
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
            return Response({"error": "deployment_blocked", "message": str(exc)}, status=status.HTTP_409_CONFLICT)
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
            return Response({"error": "deployment_blocked", "message": str(exc)}, status=409)
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
        deployment, operation = queue_rollback(source=source, release=release, requested_by=request.user.name)
        return Response(serialize_deployment(deployment, operation), status=status.HTTP_201_CREATED)


class DeploymentDetailView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:read")]

    def get(self, request, deployment_id):
        try:
            deployment = Deployment.objects.select_related("service", "active_release", "previous_release").get(public_id=deployment_id)
        except Deployment.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        data = serialize_deployment(deployment)
        data["active_release"] = deployment.active_release.name if deployment.active_release else None
        data["previous_release"] = deployment.previous_release.name if deployment.previous_release else None
        data["events"] = [
            {"id": str(item.public_id), "state": item.state, "message": item.message, "metadata": item.metadata, "created_at": item.created_at}
            for item in deployment.events.all()
        ]
        return Response(data)
