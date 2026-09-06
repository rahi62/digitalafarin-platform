from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Any

import httpx


@dataclass
class TelegramAPIError(Exception):
    code: str
    message: str
    status_code: int = 502
    retry_after: int | None = None

    def __str__(self) -> str:
        return self.message


def split_message(text: str, max_chars: int = 4096) -> list[str]:
    value = text.strip()
    if not value:
        raise ValueError("message text cannot be empty")
    if len(value) <= max_chars:
        return [value]

    chunks: list[str] = []
    remaining = value
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        candidate = remaining[:max_chars]
        split_at = candidate.rfind("\n")
        if split_at < max_chars // 2:
            split_at = candidate.rfind(" ")
        if split_at < max_chars // 2:
            split_at = max_chars
        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:max_chars]
            split_at = max_chars
        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()
    return chunks


class TelegramClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.telegram.org",
        timeout_seconds: float = 10.0,
    ):
        self._token = token.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        if not self._token:
            raise ValueError("Telegram bot token is required")

    def _post(self, method: str, payload: dict[str, Any]) -> Any:
        url = f"{self._base_url}/bot{self._token}/{method}"
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(url, json=payload)
                body = response.json()
            except (httpx.RequestError, ValueError) as exc:
                last_error = exc
                if attempt == 0:
                    sleep(0.2)
                    continue
                raise TelegramAPIError(
                    code="telegram_network_error",
                    message="Telegram API is temporarily unreachable.",
                    status_code=502,
                ) from exc

            if response.status_code >= 500 and attempt == 0:
                sleep(0.2)
                continue

            if not isinstance(body, dict) or body.get("ok") is not True:
                error_code = body.get("error_code") if isinstance(body, dict) else None
                description = body.get("description") if isinstance(body, dict) else None
                parameters = body.get("parameters", {}) if isinstance(body, dict) else {}
                retry_after = parameters.get("retry_after") if isinstance(parameters, dict) else None
                raise TelegramAPIError(
                    code=f"telegram_{error_code}" if error_code else "telegram_api_error",
                    message=str(description or "Telegram API rejected the request."),
                    status_code=429 if error_code == 429 else 502,
                    retry_after=retry_after if isinstance(retry_after, int) else None,
                )
            return body.get("result")

        raise TelegramAPIError(
            code="telegram_network_error",
            message="Telegram API is temporarily unreachable.",
            status_code=502,
        ) from last_error

    def validate_bot(self) -> dict[str, Any]:
        result = self._post("getMe", {})
        if not isinstance(result, dict):
            raise TelegramAPIError(
                code="telegram_invalid_response",
                message="Telegram returned an invalid bot identity response.",
            )
        return result

    def send_message(
        self,
        chat_id: str,
        text: str,
        disable_web_page_preview: bool = False,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for chunk in split_message(text):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
            }
            if disable_web_page_preview:
                payload["link_preview_options"] = {"is_disabled": True}
            result = self._post("sendMessage", payload)
            if not isinstance(result, dict) or not isinstance(result.get("message_id"), int):
                raise TelegramAPIError(
                    code="telegram_invalid_response",
                    message="Telegram returned an invalid sendMessage response.",
                )
            results.append(result)
        return results
