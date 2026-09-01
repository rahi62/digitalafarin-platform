import os
import secrets

from rest_framework import authentication, exceptions


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

        return (PlatformPrincipal(), None)
