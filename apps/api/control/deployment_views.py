from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.deployment_serializers import ProjectSerializer, ServiceSerializer
from control.models import Operation, Project, Server
from control.permissions import require_scope
from control.services.operations import create_operation


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
