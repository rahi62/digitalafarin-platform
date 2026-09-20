from rest_framework import serializers

from control.models import ServiceTakeover
from control.operation_serializers import StrictSerializer


EXACT_COMMIT_PATTERN = r"^[0-9a-f]{40}$"


class TakeoverPrepareSerializer(StrictSerializer):
    commit = serializers.RegexField(EXACT_COMMIT_PATTERN, max_length=40)


class ServiceTakeoverSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id")
    service_id = serializers.UUIDField(source="service.public_id")
    state = serializers.CharField()
    requested_commit = serializers.CharField()
    resolved_commit = serializers.CharField()
    source_fingerprint = serializers.CharField()
    source_snapshot = serializers.JSONField()
    release_name = serializers.CharField()
    release_path = serializers.CharField()
    previous_current_path = serializers.CharField(allow_null=True)
    managed_dropin_path = serializers.CharField()
    health_check_snapshot = serializers.JSONField()
    prepare_operation_id = serializers.SerializerMethodField()
    activate_operation_id = serializers.SerializerMethodField()
    failure_code = serializers.CharField()
    failure_message = serializers.CharField()
    queued_at = serializers.DateTimeField()
    prepared_at = serializers.DateTimeField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)

    def get_prepare_operation_id(self, obj):
        return str(obj.prepare_operation.public_id) if obj.prepare_operation_id else None

    def get_activate_operation_id(self, obj):
        return str(obj.activate_operation.public_id) if obj.activate_operation_id else None
