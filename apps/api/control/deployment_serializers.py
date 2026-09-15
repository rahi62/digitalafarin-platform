import re

from rest_framework import serializers

from control.models import Project, Server, Service
from control.operation_serializers import StrictSerializer


SAFE_PATH = re.compile(r"^(?:\.|[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)$")
SAFE_REF = re.compile(r"^[A-Za-z0-9._/-]+$")
INSTALL_KEYS = {
    Service.RUNTIME_NODE: {"package_manager", "lockfile"},
    Service.RUNTIME_DJANGO: {"requirements_file"},
}
BUILD_KEYS = {
    Service.RUNTIME_NODE: {"build_script"},
    Service.RUNTIME_DJANGO: {"migrate", "collectstatic", "gunicorn_module"},
}


class ProjectSerializer(StrictSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    name = serializers.CharField(max_length=120)
    slug = serializers.SlugField(max_length=80)

    def create(self, validated_data):
        return Project.objects.create(**validated_data)


class ServiceSerializer(StrictSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    project_id = serializers.UUIDField(source="project.public_id", read_only=True)
    name = serializers.SlugField(max_length=80)
    executor = serializers.ChoiceField(choices=[Service.EXECUTOR_SYSTEMD])
    repository = serializers.URLField(max_length=500)
    branch = serializers.RegexField(SAFE_REF.pattern, max_length=255)
    root_directory = serializers.RegexField(
        SAFE_PATH.pattern, max_length=255, default="."
    )
    runtime = serializers.ChoiceField(
        choices=[Service.RUNTIME_NODE, Service.RUNTIME_DJANGO]
    )
    install_configuration = serializers.DictField(default=dict)
    build_configuration = serializers.DictField(default=dict)
    service_port = serializers.IntegerField(min_value=1, max_value=65535)
    target_server_id = serializers.UUIDField(write_only=True)

    def validate(self, attrs):
        runtime = attrs["runtime"]
        install = attrs["install_configuration"]
        build = attrs["build_configuration"]
        if set(install) - INSTALL_KEYS[runtime]:
            raise serializers.ValidationError(
                {"install_configuration": "Unsupported install configuration field."}
            )
        if set(build) - BUILD_KEYS[runtime]:
            raise serializers.ValidationError(
                {"build_configuration": "Unsupported build configuration field."}
            )
        try:
            attrs["target_server"] = Server.objects.get(
                public_id=attrs.pop("target_server_id"), is_active=True
            )
        except Server.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"target_server_id": "Server not found."}
            ) from exc
        return attrs

    def create(self, validated_data):
        return Service.objects.create(project=self.context["project"], **validated_data)
