import re

from rest_framework import serializers

from control.models import Operation, Server


UNIT_PATTERN = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")
PROTECTED_UNIT_PREFIXES = (
    "digitalafarin-platform-",
    "digitalafarin-vps-mcp",
    "digitalafarin-telegram-mcp",
)


def is_protected_unit(unit_name: str) -> bool:
    return unit_name.startswith(PROTECTED_UNIT_PREFIXES)


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "Unknown field." for key in sorted(unknown)}
            )
        return super().to_internal_value(data)


class ServiceOperationPayloadSerializer(StrictSerializer):
    unit_name = serializers.RegexField(UNIT_PATTERN.pattern, max_length=255)


class ServiceLogsPayloadSerializer(ServiceOperationPayloadSerializer):
    lines = serializers.IntegerField(min_value=1, max_value=200, default=100)
    since_seconds = serializers.IntegerField(
        min_value=60, max_value=86400, default=3600
    )


PAYLOAD_SERIALIZERS = {
    Operation.KIND_SERVICE_START: ServiceOperationPayloadSerializer,
    Operation.KIND_SERVICE_STOP: ServiceOperationPayloadSerializer,
    Operation.KIND_SERVICE_RESTART: ServiceOperationPayloadSerializer,
    Operation.KIND_SERVICE_LOGS: ServiceLogsPayloadSerializer,
}


class OperationCreateSerializer(StrictSerializer):
    server_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=PAYLOAD_SERIALIZERS)
    payload = serializers.DictField()
    idempotency_key = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )

    def validate(self, attrs):
        try:
            server = Server.objects.get(public_id=attrs["server_id"], is_active=True)
        except Server.DoesNotExist as exc:
            raise serializers.ValidationError({"server_id": "Server not found."}) from exc
        payload_serializer = PAYLOAD_SERIALIZERS[attrs["kind"]](data=attrs["payload"])
        payload_serializer.is_valid(raise_exception=True)
        payload = payload_serializer.validated_data
        unit_name = payload["unit_name"]
        if is_protected_unit(unit_name):
            raise serializers.ValidationError({"payload": "Service unit is protected."})
        if not server.services.filter(unit_name=unit_name).exists():
            raise serializers.ValidationError({"payload": "Service unit is not managed."})
        attrs["server"] = server
        attrs["payload"] = payload
        return attrs


def serialize_operation(operation: Operation, *, include_result: bool) -> dict:
    data = {
        "id": str(operation.public_id),
        "server_id": str(operation.server.public_id),
        "kind": operation.kind,
        "state": operation.state,
        "payload": operation.payload,
        "error_code": operation.error_code,
        "error_message": operation.error_message,
        "actor": operation.actor,
        "created_at": operation.created_at,
        "claimed_at": operation.claimed_at,
        "started_at": operation.started_at,
        "completed_at": operation.completed_at,
    }
    if include_result:
        data["result"] = operation.result
    return data
