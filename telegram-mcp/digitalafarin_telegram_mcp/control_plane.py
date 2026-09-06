import re
from typing import Any

import httpx

from digitalafarin_telegram_mcp.errors import MCPDomainError


_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


class ControlPlaneClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        http: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.http = http or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http is None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self.http.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise MCPDomainError(
                "control_plane_unavailable",
                "Telegram control plane is unavailable.",
            ) from exc

        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.status_code < 400:
            if not isinstance(body, dict):
                raise MCPDomainError(
                    "control_plane_unavailable",
                    "Telegram control plane returned an invalid response.",
                )
            return body

        code = body.get("error") if isinstance(body, dict) else None
        message = body.get("message") if isinstance(body, dict) else None

        if response.status_code == 400:
            raise MCPDomainError("invalid_request", message or "The request is invalid.")
        if response.status_code in {401, 403}:
            raise MCPDomainError(
                "forbidden",
                "This Telegram MCP identity cannot perform this operation.",
            )
        if response.status_code == 404:
            raise MCPDomainError(
                "telegram_channel_not_found",
                message or "The requested Telegram channel does not exist.",
            )
        if response.status_code == 409:
            raise MCPDomainError(
                code or "telegram_not_configured",
                message or "Telegram publishing is not configured.",
            )
        if response.status_code == 429:
            data = {}
            retry_after = body.get("retry_after") if isinstance(body, dict) else None
            if isinstance(retry_after, int):
                data["retry_after"] = retry_after
            raise MCPDomainError(
                "telegram_rate_limited",
                message or "Telegram rate limited the publish request.",
                data,
            )
        raise MCPDomainError(
            "control_plane_unavailable",
            "Telegram control plane request failed.",
        )

    @staticmethod
    def _alias(channel: str) -> str:
        alias = channel.strip().lower()
        if not _ALIAS_RE.fullmatch(alias):
            raise MCPDomainError(
                "invalid_request",
                "channel must be a configured Telegram alias.",
            )
        return alias

    async def list_channels(self) -> dict[str, Any]:
        return await self._request("GET", "/api/control/v1/telegram/channels/")

    async def test_channel(self, channel: str) -> dict[str, Any]:
        alias = self._alias(channel)
        listed = await self.list_channels()
        item = next(
            (row for row in listed.get("items", []) if row.get("alias") == alias),
            None,
        )
        if not item or not item.get("id"):
            raise MCPDomainError(
                "telegram_channel_not_found",
                "The requested Telegram channel is unknown or inactive.",
            )
        return await self._request(
            "POST",
            f"/api/control/v1/telegram/channels/{item['id']}/test/",
            json={},
        )

    async def publish_message(
        self,
        channel: str,
        text: str,
        disable_web_page_preview: bool = False,
    ) -> dict[str, Any]:
        alias = self._alias(channel)
        if not text.strip():
            raise MCPDomainError("invalid_request", "text cannot be empty.")
        return await self._request(
            "POST",
            "/api/control/v1/telegram/publish/",
            json={
                "channel": alias,
                "text": text,
                "disable_web_page_preview": disable_web_page_preview,
            },
        )

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()
