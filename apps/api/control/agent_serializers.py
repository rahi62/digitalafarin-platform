from rest_framework import serializers


class EnrollRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    hostname = serializers.CharField(max_length=255)
    agent_version = serializers.CharField(max_length=64)
    capabilities = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        default=list,
    )


class MetricsSerializer(serializers.Serializer):
    cpu_percent = serializers.FloatField(min_value=0, max_value=100)
    memory_percent = serializers.FloatField(min_value=0, max_value=100)
    disk_percent = serializers.FloatField(min_value=0, max_value=100)
    uptime_seconds = serializers.IntegerField(min_value=0)


class ServiceHeartbeatSerializer(serializers.Serializer):
    unit_name = serializers.RegexField(r"^[A-Za-z0-9_.@:-]+$", max_length=255)
    description = serializers.CharField(
        max_length=500,
        allow_blank=True,
        required=False,
        default="",
    )
    load_state = serializers.CharField(max_length=32)
    active_state = serializers.CharField(max_length=32)
    sub_state = serializers.CharField(max_length=32)


class HeartbeatRequestSerializer(serializers.Serializer):
    agent_version = serializers.CharField(max_length=64)
    hostname = serializers.CharField(max_length=255)
    capabilities = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        default=list,
    )
    metrics = MetricsSerializer()
    services = ServiceHeartbeatSerializer(many=True)


class OperationStartedSerializer(serializers.Serializer):
    claim_token = serializers.CharField(max_length=64)


class OperationProgressSerializer(OperationStartedSerializer):
    state = serializers.ChoiceField(
        choices=[
            "preparing", "cloning", "building", "releasing",
            "health_check", "activating", "verifying",
        ]
    )
    message = serializers.CharField(max_length=500, required=False, default="", allow_blank=True)


class OperationCompleteSerializer(OperationStartedSerializer):
    succeeded = serializers.BooleanField()
    result = serializers.DictField(required=False, default=dict)
    error_code = serializers.CharField(max_length=100, required=False, default="")
    error_message = serializers.CharField(max_length=500, required=False, default="")
