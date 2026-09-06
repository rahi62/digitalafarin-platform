from rest_framework import serializers

from control.models import TelegramChannel, TelegramPublishAudit


class TelegramBotCredentialWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False, default="primary")
    token = serializers.CharField(min_length=20, max_length=512, trim_whitespace=True, write_only=True)


class TelegramChannelSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = TelegramChannel
        fields = [
            "id",
            "alias",
            "name",
            "chat_id",
            "is_active",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_alias(self, value: str) -> str:
        return value.strip().lower()


class TelegramPublishSerializer(serializers.Serializer):
    channel = serializers.CharField(max_length=80, trim_whitespace=True)
    text = serializers.CharField(max_length=100_000, trim_whitespace=False)
    disable_web_page_preview = serializers.BooleanField(required=False, default=False)

    def validate_channel(self, value: str) -> str:
        return value.strip().lower()

    def validate_text(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("message text cannot be empty")
        return value


class TelegramAuditSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    channel = serializers.SerializerMethodField()

    class Meta:
        model = TelegramPublishAudit
        fields = [
            "id",
            "channel",
            "action",
            "status",
            "message_ids",
            "content_preview",
            "error_code",
            "error_message",
            "actor_principal",
            "created_at",
        ]

    def get_channel(self, obj):
        return obj.channel.alias if obj.channel_id else None
