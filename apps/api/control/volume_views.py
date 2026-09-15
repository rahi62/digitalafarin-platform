import re

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.models import Operation, Project, Service, Volume
from control.operation_serializers import StrictSerializer
from control.permissions import require_scope
from control.services.operations import create_operation


class VolumeCreateSerializer(StrictSerializer):
    name = serializers.SlugField(max_length=80)
    service_id = serializers.UUIDField()
    mount_path = serializers.RegexField(r"^/(?:[A-Za-z0-9_.-]+/?)+$", max_length=500)
    owner = serializers.RegexField(r"^[a-z_][a-z0-9_-]{0,63}$")
    group = serializers.RegexField(r"^[a-z_][a-z0-9_-]{0,63}$")
    mode = serializers.RegexField(r"^0[0-7]{3}$")
    backup_policy = serializers.ChoiceField(choices=["none", "daily"])

    def validate_service_id(self, value):
        try:
            return Service.objects.get(public_id=value, project=self.context["project"])
        except Service.DoesNotExist as exc:
            raise serializers.ValidationError("Service not found.") from exc


def serialize_volume(volume: Volume, operation=None):
    data = {
        "id": str(volume.public_id),
        "project_id": str(volume.project.public_id),
        "service_id": str(volume.service.public_id),
        "server_id": str(volume.server.public_id),
        "name": volume.name,
        "host_path": volume.host_path,
        "mount_path": volume.mount_path,
        "owner": volume.owner,
        "group": volume.group,
        "mode": volume.mode,
        "backup_policy": volume.backup_policy,
    }
    if operation is not None:
        data.update(operation_id=str(operation.public_id), operation_state=operation.state)
    return data


class VolumeListCreateView(APIView):
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
        return Response({"items": [serialize_volume(item) for item in project.volumes.all()]})

    @transaction.atomic
    def post(self, request, project_id):
        project = self._project(project_id)
        if project is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = VolumeCreateSerializer(data=request.data, context={"project": project})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        service = data.pop("service_id")
        volume = Volume.objects.create(
            project=project,
            service=service,
            server=service.target_server,
            host_path=f"/srv/digitalafarin/volumes/{project.slug}/{data['name']}",
            **data,
        )
        operation = create_operation(
            server=service.target_server,
            kind=Operation.KIND_VOLUME_CREATE,
            payload={
                "project_slug": project.slug,
                "name": volume.name,
                "owner": volume.owner,
                "group": volume.group,
                "mode": volume.mode,
            },
            actor=request.user.name,
        )
        return Response(serialize_volume(volume, operation), status=status.HTTP_201_CREATED)
