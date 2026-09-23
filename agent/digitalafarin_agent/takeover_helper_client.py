import json
import os
import socket
from pathlib import Path
from typing import Any


DEFAULT_SOCKET_PATH = Path(
    os.environ.get(
        "DIGITALAFARIN_TAKEOVER_HELPER_SOCKET",
        "/run/digitalafarin-takeover/helper.sock",
    )
)
MAX_RESPONSE_BYTES = 256 * 1024


class TakeoverHelperError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TakeoverHelperClient:
    def __init__(
        self,
        socket_path: str | Path | None = None,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.socket_path = Path(socket_path) if socket_path else DEFAULT_SOCKET_PATH
        self.timeout = timeout

    def call(
        self,
        operation: str,
        params: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not isinstance(operation, str) or not operation:
            raise TakeoverHelperError("helper_invalid_request", "Invalid helper operation.")
        if not isinstance(params, dict):
            raise TakeoverHelperError("helper_invalid_request", "Invalid helper parameters.")

        request = {
            "protocol": 1,
            "operation": operation,
            "params": params,
        }
        raw = (json.dumps(request, separators=(",", ":"), ensure_ascii=True) + "\n").encode(
            "utf-8"
        )
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout if timeout is None else timeout)
                client.connect(str(self.socket_path))
                client.sendall(raw)
                client.shutdown(socket.SHUT_WR)
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise TakeoverHelperError(
                            "helper_protocol_error", "Helper response exceeded limit."
                        )
                    chunks.append(chunk)
                    if b"\n" in chunk:
                        break
        except TakeoverHelperError:
            raise
        except (OSError, TimeoutError) as exc:
            raise TakeoverHelperError(
                "helper_unavailable", "Privileged takeover helper is unavailable."
            ) from exc

        payload = b"".join(chunks).split(b"\n", 1)[0]
        try:
            response = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TakeoverHelperError(
                "helper_protocol_error", "Invalid response from takeover helper."
            ) from exc
        if not isinstance(response, dict) or set(response) not in (
            {"ok", "result"},
            {"ok", "error"},
        ):
            raise TakeoverHelperError(
                "helper_protocol_error", "Invalid response from takeover helper."
            )
        if response.get("ok") is True:
            result = response.get("result")
            if not isinstance(result, dict):
                raise TakeoverHelperError(
                    "helper_protocol_error", "Invalid helper result."
                )
            return result
        error = response.get("error")
        if not isinstance(error, dict):
            raise TakeoverHelperError(
                "helper_protocol_error", "Invalid helper error response."
            )
        code = error.get("code")
        message = error.get("message")
        if not isinstance(code, str) or not code or not isinstance(message, str):
            raise TakeoverHelperError(
                "helper_protocol_error", "Invalid helper error response."
            )
        raise TakeoverHelperError(code, message)

    def prepare_node_nextjs_release(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.call("prepare_node_nextjs_release", params, timeout=1200)

    def activate_release(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.call("activate_release", params)

    def rollback_activation(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.call("rollback_activation", params)

    def cleanup_release(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.call("cleanup_release", params)

    def prepare_managed_node_nextjs_release(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.call("prepare_managed_node_nextjs_release", params, timeout=3000)

    def activate_managed_release(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.call("activate_managed_release", params, timeout=120)

    def rollback_managed_activation(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.call("rollback_managed_activation", params, timeout=120)

    def rollback_managed_release(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.call("rollback_managed_release", params, timeout=120)

    def prune_managed_releases(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.call("prune_managed_releases", params, timeout=300)
