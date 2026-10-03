import re

from rest_framework import serializers

from control.models import Project, Server, Service
from control.operation_serializers import StrictSerializer, UNIT_PATTERN, is_protected_unit


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


def validate_deployment_configuration(attrs):
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
    return attrs


class ProjectSerializer(StrictSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    name = serializers.CharField(max_length=120)
    slug = serializers.SlugField(max_length=80)

    def validate_slug(self, value):
        queryset = Project.objects.filter(slug=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("A project with this slug already exists.")
        return value

    def create(self, validated_data):
        return Project.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*validated_data.keys(), "updated_at"])
        return instance


class ServiceSerializer(StrictSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    project_id = serializers.UUIDField(source="project.public_id", read_only=True)
    name = serializers.SlugField(max_length=80)
    executor = serializers.ChoiceField(choices=[Service.EXECUTOR_SYSTEMD])
    unit_name = serializers.CharField(read_only=True)
    lifecycle_state = serializers.ChoiceField(
        choices=Service.LIFECYCLE_CHOICES, read_only=True
    )
    repository = serializers.URLField(max_length=500)
    branch = serializers.RegexField(SAFE_REF.pattern, max_length=255)
    auto_deploy = serializers.BooleanField(default=False)
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
        try:
            attrs["target_server"] = Server.objects.get(
                public_id=attrs.pop("target_server_id"), is_active=True
            )
        except Server.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"target_server_id": "Server not found."}
            ) from exc
        return validate_deployment_configuration(attrs)

    def create(self, validated_data):
        project = self.context["project"]
        name = validated_data["name"]
        return Service.objects.create(
            project=project,
            unit_name=f"{project.slug}-{name}.service",
            lifecycle_state=Service.LIFECYCLE_MANAGED,
            **validated_data,
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["target_server_id"] = str(instance.target_server.public_id)
        snapshot = instance.target_server.services.filter(unit_name=instance.unit_name).first()
        data["protected"] = is_protected_unit(instance.unit_name)
        if snapshot is None:
            data.update(
                inventory_status="missing",
                load_state=None,
                active_state=None,
                sub_state=None,
                inventory_last_seen_at=None,
            )
        else:
            data.update(
                inventory_status="present",
                load_state=snapshot.load_state,
                active_state=snapshot.active_state,
                sub_state=snapshot.sub_state,
                inventory_last_seen_at=snapshot.last_seen_at,
            )
        return data


class AdoptServiceSerializer(StrictSerializer):
    server_id = serializers.UUIDField()
    unit_name = serializers.RegexField(UNIT_PATTERN.pattern, max_length=255)
    name = serializers.SlugField(max_length=80)


class DeploymentConfigurationSerializer(StrictSerializer):
    repository = serializers.URLField(max_length=500)
    branch = serializers.RegexField(SAFE_REF.pattern, max_length=255)
    root_directory = serializers.RegexField(SAFE_PATH.pattern, max_length=255, default=".")
    runtime = serializers.ChoiceField(choices=[Service.RUNTIME_NODE, Service.RUNTIME_DJANGO])
    install_configuration = serializers.DictField(default=dict)
    build_configuration = serializers.DictField(default=dict)
    service_port = serializers.IntegerField(min_value=1, max_value=65535)

    def validate(self, attrs):
        return validate_deployment_configuration(attrs)


class ServiceSettingsSerializer(StrictSerializer):
    repository = serializers.URLField(max_length=500)
    branch = serializers.RegexField(SAFE_REF.pattern, max_length=255)
    root_directory = serializers.RegexField(SAFE_PATH.pattern, max_length=255, default=".")
    runtime = serializers.ChoiceField(choices=[Service.RUNTIME_NODE, Service.RUNTIME_DJANGO])
    install_configuration = serializers.DictField(default=dict)
    build_configuration = serializers.DictField(default=dict)
    service_port = serializers.IntegerField(min_value=1, max_value=65535)

    def validate(self, attrs):
        return validate_deployment_configuration(attrs)

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*validated_data.keys(), "updated_at"])
        return instance
