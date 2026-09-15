import re
import secrets

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.models import DatabaseResource, Operation, Project, Service
from control.operation_serializers import StrictSerializer
from control.permissions import require_scope
from control.services.operations import create_operation
from control.services.secrets import encrypt_secret


IDENTIFIER = r"^[a-z_][a-z0-9_]{0,62}$"


class DatabaseCreateSerializer(StrictSerializer):
    service_id = serializers.UUIDField()
    database_name = serializers.RegexField(IDENTIFIER)
    username = serializers.RegexField(IDENTIFIER)

    def validate_service_id(self, value):
        try:
            return Service.objects.get(public_id=value, project=self.context["project"])
        except Service.DoesNotExist as exc:
            raise serializers.ValidationError("Service not found.") from exc


class DatabaseRestoreSerializer(StrictSerializer):
    backup_name = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")


def serialize_database(database: DatabaseResource, operation=None):
    data = {
        "id": str(database.public_id),
        "project_id": str(database.project.public_id),
        "service_id": str(database.service.public_id),
        "server_id": str(database.server.public_id),
        "database_name": database.database_name,
        "username": database.username,
        "status": database.status,
        "has_credential": bool(database.password_ciphertext),
        "last_backup_name": database.last_backup_name,
    }
    if operation:
        data.update(operation_id=str(operation.public_id), operation_state=operation.state)
    return data


class DatabaseListCreateView(APIView):
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
        return Response({"items": [serialize_database(item) for item in project.databases.all()]})

    @transaction.atomic
    def post(self, request, project_id):
        project = self._project(project_id)
        if project is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = DatabaseCreateSerializer(data=request.data, context={"project": project})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        service = data.pop("service_id")
        database = DatabaseResource.objects.create(
            project=project,
            service=service,
            server=service.target_server,
            password_ciphertext=encrypt_secret(secrets.token_urlsafe(32)),
            **data,
        )
        operation = create_operation(
            server=database.server,
            kind=Operation.KIND_DATABASE_CREATE,
            payload={"database_resource_id": str(database.public_id)},
            actor=request.user.name,
        )
        return Response(serialize_database(database, operation), status=status.HTTP_201_CREATED)


class DatabaseRestoreView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    @transaction.atomic
    def post(self, request, database_id):
        serializer = DatabaseRestoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            database = DatabaseResource.objects.get(public_id=database_id)
        except DatabaseResource.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        backup_name = serializer.validated_data["backup_name"]
        database.last_backup_name = backup_name
        database.save(update_fields=["last_backup_name", "updated_at"])
        operation = create_operation(
            server=database.server,
            kind=Operation.KIND_DATABASE_RESTORE,
            payload={"database_resource_id": str(database.public_id), "backup_name": backup_name},
            actor=request.user.name,
        )
        return Response(serialize_database(database, operation), status=status.HTTP_201_CREATED)
