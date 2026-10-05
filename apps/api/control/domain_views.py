from django.db import transaction
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.models import Domain, Operation, Project, Service
from control.operation_serializers import StrictSerializer
from control.permissions import require_scope
from control.services.operations import create_operation


class DomainCreateSerializer(StrictSerializer):
    service_id = serializers.UUIDField()
    hostname = serializers.RegexField(
        r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
    )
    configure_nginx = serializers.BooleanField(default=True)
    ssl_enabled = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if attrs["configure_nginx"] and attrs["ssl_enabled"]:
            raise serializers.ValidationError(
                {"ssl_enabled": "Managed domains must enable SSL through the SSL operation."}
            )
        return attrs

    def validate_service_id(self, value):
        try:
            return Service.objects.get(public_id=value, project=self.context["project"])
        except Service.DoesNotExist as exc:
            raise serializers.ValidationError("Service not found.") from exc


def serialize_domain(domain, operation=None):
    data = {
        "id": str(domain.public_id),
        "project_id": str(domain.project.public_id),
        "service_id": str(domain.service.public_id),
        "server_id": str(domain.server.public_id),
        "hostname": domain.hostname,
        "status": domain.status,
        "ssl_enabled": domain.ssl_enabled,
        "management_mode": "external" if domain.status == "external" else "platform",
    }
    if operation:
        data["operation_id"] = str(operation.public_id)
    return data


class DomainListCreateView(APIView):
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
        return Response({"items": [serialize_domain(item) for item in project.domains.all()]})

    @transaction.atomic
    def post(self, request, project_id):
        project = self._project(project_id)
        if project is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = DomainCreateSerializer(data=request.data, context={"project": project})
        serializer.is_valid(raise_exception=True)
        service = serializer.validated_data["service_id"]
        configure_nginx = serializer.validated_data["configure_nginx"]
        domain = Domain.objects.create(
            project=project,
            service=service,
            server=service.target_server,
            hostname=serializer.validated_data["hostname"],
            status="queued" if configure_nginx else "external",
            ssl_enabled=serializer.validated_data["ssl_enabled"] if not configure_nginx else False,
        )
        if not configure_nginx:
            return Response(serialize_domain(domain), status=status.HTTP_201_CREATED)
        operation = create_operation(
            server=domain.server,
            kind=Operation.KIND_DOMAIN_CONFIGURE,
            payload={"domain_id": str(domain.public_id)},
            actor=request.user.name,
        )
        return Response(serialize_domain(domain, operation), status=status.HTTP_201_CREATED)


class DomainSSLView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def post(self, request, domain_id):
        if request.data:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        try:
            domain = Domain.objects.get(public_id=domain_id)
        except Domain.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        operation = create_operation(
            server=domain.server,
            kind=Operation.KIND_DOMAIN_SSL,
            payload={"domain_id": str(domain.public_id)},
            actor=request.user.name,
        )
        return Response(serialize_domain(domain, operation), status=status.HTTP_201_CREATED)
