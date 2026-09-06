from hashlib import sha256

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.models import (
    TelegramBotCredential,
    TelegramChannel,
    TelegramPublishAudit,
)
from control.permissions import require_scope
from control.telegram_client import TelegramAPIError, TelegramClient
from control.telegram_crypto import decrypt_bot_token, encrypt_bot_token
from control.telegram_serializers import (
    TelegramAuditSerializer,
    TelegramBotCredentialWriteSerializer,
    TelegramChannelSerializer,
    TelegramPublishSerializer,
)


def _actor(request) -> str:
    return getattr(request.user, "name", str(request.user))[:120]


def _content_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _telegram_error_response(exc: TelegramAPIError) -> Response:
    body = {"error": exc.code, "message": exc.message}
    if exc.retry_after is not None:
        body["retry_after"] = exc.retry_after
    return Response(body, status=exc.status_code)


def _active_credential() -> TelegramBotCredential | None:
    return TelegramBotCredential.objects.filter(is_active=True).order_by("-updated_at").first()


def _load_client() -> TelegramClient:
    credential = _active_credential()
    if credential is None:
        raise RuntimeError("Telegram bot credential is not configured")
    return TelegramClient(decrypt_bot_token(credential.token_ciphertext))


def _config_error(message: str) -> Response:
    return Response(
        {"error": "telegram_not_configured", "message": message},
        status=status.HTTP_409_CONFLICT,
    )


def _create_audit(
    request,
    *,
    channel: TelegramChannel | None,
    action: str,
    outcome: str,
    text: str = "",
    message_ids: list[int] | None = None,
    error_code: str = "",
    error_message: str = "",
) -> TelegramPublishAudit:
    return TelegramPublishAudit.objects.create(
        channel=channel,
        action=action,
        status=outcome,
        message_ids=message_ids or [],
        content_preview=text[:280],
        content_sha256=_content_hash(text) if text else "",
        error_code=error_code[:100],
        error_message=error_message[:500],
        actor_principal=_actor(request),
    )


class TelegramControlAPIView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]


class TelegramStatusView(TelegramControlAPIView):
    permission_classes = [require_scope("telegram:read")]

    def get(self, request):
        credential = _active_credential()
        return Response(
            {
                "bot_configured": credential is not None,
                "bot_name": credential.name if credential else None,
                "bot_active": bool(credential and credential.is_active),
                "active_channels": TelegramChannel.objects.filter(is_active=True).count(),
            }
        )


class TelegramBotCredentialView(TelegramControlAPIView):
    permission_classes = [require_scope("telegram:admin")]

    def put(self, request):
        serializer = TelegramBotCredentialWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data["token"]
        name = serializer.validated_data["name"].strip() or "primary"

        try:
            bot = TelegramClient(token).validate_bot()
            ciphertext = encrypt_bot_token(token)
        except TelegramAPIError as exc:
            return _telegram_error_response(exc)
        except (RuntimeError, ValueError) as exc:
            return Response(
                {"error": "telegram_configuration_error", "message": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        with transaction.atomic():
            credential, _ = TelegramBotCredential.objects.update_or_create(
                name=name,
                defaults={"token_ciphertext": ciphertext, "is_active": True},
            )
            TelegramBotCredential.objects.exclude(pk=credential.pk).update(is_active=False)

        return Response(
            {
                "configured": True,
                "name": credential.name,
                "bot_id": bot.get("id"),
                "bot_username": bot.get("username"),
            }
        )


class TelegramChannelListView(TelegramControlAPIView):
    def get_permissions(self):
        scope = "telegram:admin" if self.request.method == "POST" else "telegram:read"
        return [require_scope(scope)()]

    def get(self, request):
        qs = TelegramChannel.objects.all()
        if "telegram:admin" not in set(getattr(request.user, "scopes", [])):
            qs = qs.filter(is_active=True)
        return Response({"items": TelegramChannelSerializer(qs, many=True).data})

    def post(self, request):
        serializer = TelegramChannelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channel = serializer.save()
        return Response(
            TelegramChannelSerializer(channel).data,
            status=status.HTTP_201_CREATED,
        )


class TelegramChannelDetailView(TelegramControlAPIView):
    permission_classes = [require_scope("telegram:admin")]

    def patch(self, request, channel_id):
        channel = get_object_or_404(TelegramChannel, public_id=channel_id)
        serializer = TelegramChannelSerializer(channel, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        channel = serializer.save()
        return Response(TelegramChannelSerializer(channel).data)


class TelegramChannelTestView(TelegramControlAPIView):
    permission_classes = [require_scope("telegram:publish")]

    def post(self, request, channel_id):
        channel = get_object_or_404(TelegramChannel, public_id=channel_id)
        text = "DigitalAfarin Telegram channel test ✅"
        try:
            client = _load_client()
            sent = client.send_message(channel.chat_id, text)
            message_ids = [item["message_id"] for item in sent]
        except TelegramAPIError as exc:
            _create_audit(
                request,
                channel=channel,
                action=TelegramPublishAudit.ACTION_TEST,
                outcome=TelegramPublishAudit.STATUS_FAILED,
                text=text,
                error_code=exc.code,
                error_message=exc.message,
            )
            return _telegram_error_response(exc)
        except RuntimeError as exc:
            _create_audit(
                request,
                channel=channel,
                action=TelegramPublishAudit.ACTION_TEST,
                outcome=TelegramPublishAudit.STATUS_FAILED,
                text=text,
                error_code="telegram_not_configured",
                error_message=str(exc),
            )
            return _config_error(str(exc))

        _create_audit(
            request,
            channel=channel,
            action=TelegramPublishAudit.ACTION_TEST,
            outcome=TelegramPublishAudit.STATUS_SUCCESS,
            text=text,
            message_ids=message_ids,
        )
        return Response({"ok": True, "channel": channel.alias, "message_ids": message_ids})


class TelegramAuditListView(TelegramControlAPIView):
    permission_classes = [require_scope("telegram:admin")]

    def get(self, request):
        try:
            limit = max(1, min(int(request.query_params.get("limit", "30")), 100))
        except ValueError:
            return Response(
                {"error": "invalid_request", "message": "limit must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        items = TelegramPublishAudit.objects.select_related("channel")[:limit]
        return Response({"items": TelegramAuditSerializer(items, many=True).data})


class TelegramPublishView(TelegramControlAPIView):
    permission_classes = [require_scope("telegram:publish")]

    def post(self, request):
        serializer = TelegramPublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alias = serializer.validated_data["channel"]
        text = serializer.validated_data["text"]
        disable_preview = serializer.validated_data["disable_web_page_preview"]

        channel = TelegramChannel.objects.filter(alias=alias, is_active=True).first()
        if channel is None:
            return Response(
                {
                    "error": "telegram_channel_not_found",
                    "message": "The requested Telegram channel is unknown or inactive.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            client = _load_client()
            sent = client.send_message(
                channel.chat_id,
                text,
                disable_web_page_preview=disable_preview,
            )
            message_ids = [item["message_id"] for item in sent]
        except TelegramAPIError as exc:
            _create_audit(
                request,
                channel=channel,
                action=TelegramPublishAudit.ACTION_PUBLISH,
                outcome=TelegramPublishAudit.STATUS_FAILED,
                text=text,
                error_code=exc.code,
                error_message=exc.message,
            )
            return _telegram_error_response(exc)
        except RuntimeError as exc:
            _create_audit(
                request,
                channel=channel,
                action=TelegramPublishAudit.ACTION_PUBLISH,
                outcome=TelegramPublishAudit.STATUS_FAILED,
                text=text,
                error_code="telegram_not_configured",
                error_message=str(exc),
            )
            return _config_error(str(exc))

        _create_audit(
            request,
            channel=channel,
            action=TelegramPublishAudit.ACTION_PUBLISH,
            outcome=TelegramPublishAudit.STATUS_SUCCESS,
            text=text,
            message_ids=message_ids,
        )
        return Response(
            {
                "ok": True,
                "channel": channel.alias,
                "message_ids": message_ids,
            }
        )
