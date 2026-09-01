from rest_framework import serializers

from .models import AuditEvent, Server, ServiceSnapshot


class ServiceSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceSnapshot
        fields = [
            "id", "unit_name", "description", "load_state", "active_state",
            "sub_state", "last_seen_at",
        ]


class ServerSerializer(serializers.ModelSerializer):
    services = ServiceSnapshotSerializer(many=True, read_only=True)

    class Meta:
        model = Server
        fields = [
            "id", "name", "hostname", "agent_url", "is_active", "last_seen_at",
            "cpu_percent", "memory_percent", "disk_percent", "uptime_seconds",
            "services",
        ]
        read_only_fields = [
            "last_seen_at", "cpu_percent", "memory_percent", "disk_percent", "uptime_seconds"
        ]


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["id", "event_type", "target_type", "target_id", "actor", "metadata", "created_at"]
