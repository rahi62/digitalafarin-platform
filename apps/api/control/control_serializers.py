from rest_framework import serializers

from control.models import AuditEvent, Server, ServiceSnapshot


class ServerReadSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status = serializers.CharField(read_only=True)
    age_seconds = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Server
        fields = [
            "id",
            "name",
            "hostname",
            "is_default",
            "status",
            "last_seen_at",
            "age_seconds",
            "agent_version",
            "capabilities",
        ]


class MetricsReadSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status = serializers.CharField(read_only=True)
    age_seconds = serializers.IntegerField(read_only=True, allow_null=True)
    stale = serializers.BooleanField(source="is_stale", read_only=True)
    collected_at = serializers.DateTimeField(
        source="last_seen_at",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Server
        fields = [
            "id",
            "name",
            "status",
            "cpu_percent",
            "memory_percent",
            "disk_percent",
            "uptime_seconds",
            "collected_at",
            "age_seconds",
            "stale",
        ]


class ServiceReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceSnapshot
        fields = [
            "unit_name",
            "description",
            "load_state",
            "active_state",
            "sub_state",
            "last_seen_at",
        ]


class AuditReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "event_type",
            "target_type",
            "target_id",
            "actor",
            "metadata",
            "created_at",
        ]
