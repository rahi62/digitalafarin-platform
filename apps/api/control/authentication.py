import os
import secrets

from django.utils import timezone
from rest_framework import authentication, exceptions

from control.models import AgentCredential
from control.security import parse_secret, verify_secret


class PlatformPrincipal:
    is_authenticated = True
    username = "platform-token"

    def __str__(self) -> str:
        return self.username


class PlatformTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        expected = os.getenv("PLATFORM_API_TOKEN", "")
        if not expected:
            raise exceptions.AuthenticationFailed("PLATFORM_API_TOKEN is not configured")

        raw = request.headers.get("Authorization", "")
        prefix = f"{self.keyword} "
        if not raw.startswith(prefix):
            raise exceptions.AuthenticationFailed("Missing bearer token")

        supplied = raw[len(prefix):].strip()
        if not secrets.compare_digest(supplied, expected):
            raise exceptions.AuthenticationFailed("Invalid bearer token")

        return PlatformPrincipal(), None

    def authenticate_header(self, request):
        return self.keyword


class AgentPrincipal:
    is_authenticated = True

    def __init__(self, credential: AgentCredential):
        self.credential = credential
        self.server = credential.server
        self.username = f"agent:{self.server.public_id}"

    def __str__(self) -> str:
        return self.username


class AgentTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        raw = request.headers.get("Authorization", "")
        prefix = f"{self.keyword} "
        if not raw.startswith(prefix):
            raise exceptions.AuthenticationFailed("Invalid agent credential")
        try:
            token_prefix, secret = parse_secret(raw[len(prefix):].strip(), "agent")
            credential = AgentCredential.objects.select_related("server").get(
                token_prefix=token_prefix,
                revoked_at__isnull=True,
                server__is_active=True,
            )
        except (ValueError, AgentCredential.DoesNotExist) as exc:
            raise exceptions.AuthenticationFailed("Invalid agent credential") from exc
        if not verify_secret(secret, credential.token_hash):
            raise exceptions.AuthenticationFailed("Invalid agent credential")
        credential.last_used_at = timezone.now()
        credential.save(update_fields=["last_used_at"])
        return AgentPrincipal(credential), credential

    def authenticate_header(self, request):
        return self.keyword
