import re

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.models import EnvironmentVariable, Project, Service
from control.operation_serializers import StrictSerializer
from control.permissions import require_scope
from control.services.secrets import encrypt_secret


class EnvironmentVariableSerializer(StrictSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    key = serializers.RegexField(r"^[A-Z_][A-Z0-9_]{0,127}$")
    value = serializers.CharField(write_only=True, allow_blank=False)
    value_type = serializers.ChoiceField(choices=["plain", "secret"])
    scope = serializers.ChoiceField(choices=["project", "service", "environment"])
    service_id = serializers.UUIDField(required=False, allow_null=True)
    environment = serializers.SlugField(required=False, allow_blank=True, default="")
    target = serializers.ChoiceField(choices=["build", "runtime", "both"], default="both")
    has_value = serializers.SerializerMethodField(read_only=True)

    def validate(self, attrs):
        project = self.context["project"]
        scope = attrs["scope"]
        service_id = attrs.pop("service_id", None)
        if scope == "project":
            if service_id or attrs["environment"]:
                raise serializers.ValidationError("Project variables cannot select a service or environment.")
            attrs["service"] = None
        else:
            try:
                attrs["service"] = Service.objects.get(
                    public_id=service_id, project=project
                )
            except Service.DoesNotExist as exc:
                raise serializers.ValidationError({"service_id": "Service not found."}) from exc
            if scope == "service" and attrs["environment"]:
                raise serializers.ValidationError("Service variables cannot select an environment.")
            if scope == "environment" and not attrs["environment"]:
                raise serializers.ValidationError({"environment": "This field is required."})
        return attrs

    def create(self, validated_data):
        value = validated_data.pop("value")
        if validated_data["value_type"] == "secret":
            validated_data["secret_ciphertext"] = encrypt_secret(value)
        else:
            validated_data["plain_value"] = value
        return EnvironmentVariable.objects.create(
            project=self.context["project"], **validated_data
        )

    def get_has_value(self, obj):
        return bool(obj.secret_ciphertext or obj.plain_value)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.value_type == EnvironmentVariable.TYPE_PLAIN:
            data["value"] = instance.plain_value
        return data


class EnvironmentVariableListCreateView(APIView):
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
            {
                "items": EnvironmentVariableSerializer(
                    project.environment_variables.all(), many=True
                ).data
            }
        )

    def post(self, request, project_id):
        project = self._project(project_id)
        if project is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = EnvironmentVariableSerializer(
            data=request.data, context={"project": project}
        )
        serializer.is_valid(raise_exception=True)
        variable = serializer.save()
        return Response(
            EnvironmentVariableSerializer(variable).data,
            status=status.HTTP_201_CREATED,
        )
