"""Narrow Coolify contracts: never accept commands, raw Docker/Compose, or URLs with credentials."""
from collections.abc import Mapping
from decimal import Decimal
from urllib.parse import urlsplit

from rest_framework import serializers
from control.operation_serializers import StrictSerializer as BaseStrictSerializer, is_protected_unit

IDENTIFIER = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$"


class StrictSerializer(BaseStrictSerializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({"non_field_errors": ["Expected an object."]})
        return super().to_internal_value(data)


class IdentifierField(serializers.RegexField):
    def __init__(self, **kwargs):
        super().__init__(IDENTIFIER, max_length=80, **kwargs)


class RepositoryField(serializers.URLField):
    def __init__(self, **kwargs):
        super().__init__(max_length=500, **kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        url = urlsplit(value)
        if url.scheme != "https" or url.username or url.password or url.query or url.fragment:
            raise serializers.ValidationError("Use a credential-free HTTPS repository URL.")
        return value


class DirectoryField(serializers.RegexField):
    def __init__(self, **kwargs):
        super().__init__(r"^/[A-Za-z0-9_./-]*$", max_length=200, **kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if any(part in {".", ".."} for part in value.split("/")) or "//" in value:
            raise serializers.ValidationError("Use a repository-relative directory starting with /.")
        return value


class ApplicationSettingsSerializer(StrictSerializer):
    git_repository = RepositoryField(required=False)
    git_branch = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,199}$", required=False)
    base_directory = DirectoryField(required=False)
    build_pack = serializers.ChoiceField(choices=["nixpacks", "railpack", "static", "dockerfile"], required=False)
    publish_directory = DirectoryField(required=False)
    ports_exposes = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=65535), min_length=1, max_length=16, required=False)
    domains = serializers.ListField(child=serializers.URLField(max_length=253), max_length=10, required=False)
    is_static = serializers.BooleanField(required=False)
    limits_memory = serializers.RegexField(r"^(?:[1-9][0-9]{0,3})(?:M|G)$", required=False)
    limits_cpus = serializers.DecimalField(max_digits=4, decimal_places=2, min_value=Decimal("0.1"), max_value=Decimal("64"), required=False)

    def validate_git_branch(self, value):
        if ".." in value or "//" in value or value.endswith(("/", ".", ".lock")):
            raise serializers.ValidationError("Invalid Git branch.")
        return value

    def validate_domains(self, values):
        for value in values:
            url = urlsplit(value)
            try:
                port = url.port
            except ValueError:
                raise serializers.ValidationError("Invalid domain port.") from None
            if url.scheme != "https" or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"} or port:
                raise serializers.ValidationError("Use HTTPS origins without credentials, paths, or ports.")
        return values


class ApplicationCreateSerializer(ApplicationSettingsSerializer):
    request_id = serializers.UUIDField()
    target = IdentifierField()
    name = serializers.RegexField(r"^[a-z][a-z0-9-]{0,79}$")
    git_repository = RepositoryField()
    git_branch = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,199}$")
    build_pack = serializers.ChoiceField(choices=["nixpacks", "railpack", "static", "dockerfile"])
    ports_exposes = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=65535), min_length=1, max_length=16)

    def validate_name(self, value):
        if protected_name(value):
            raise serializers.ValidationError("Protected application name.")
        return value


def protected_name(value):
    value = str(value).lower()
    return is_protected_unit(value) or any(word in value for word in ("mcp", "tunnel", "coolify", "digitalafarin-platform"))


class EnvironmentWriteSerializer(StrictSerializer):
    key = serializers.RegexField(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
    value = serializers.CharField(max_length=16384, allow_blank=True, trim_whitespace=False, write_only=True)
    is_buildtime = serializers.BooleanField(default=False)
    is_runtime = serializers.BooleanField(default=True)

    def validate_key(self, value):
        # Buildpack/runtime control variables are command/configuration inputs,
        # not ordinary app secrets. Do not bypass the no-command contract.
        if value.upper().startswith(("NIXPACKS_", "RAILPACK_", "NPM_CONFIG_", "NODE_OPTIONS", "LD_", "BASH_", "SHELLOPTS", "PYTHONPATH", "PYTHONSTARTUP")) or value.upper().endswith(("_COMMAND", "_CMD")):
            raise serializers.ValidationError("Reserved environment variable.")
        return value

    def validate(self, attrs):
        if not attrs["is_buildtime"] and not attrs["is_runtime"]:
            raise serializers.ValidationError("At least one variable target is required.")
        return attrs


class DeleteSerializer(StrictSerializer):
    confirm_application_uuid = IdentifierField()


class LogQuerySerializer(StrictSerializer):
    lines = serializers.IntegerField(min_value=1, max_value=200, default=100)


class EmptySerializer(StrictSerializer):
    pass
