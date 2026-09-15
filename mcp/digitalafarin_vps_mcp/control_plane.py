import re
from urllib.parse import quote

import httpx

from digitalafarin_vps_mcp.errors import MCPDomainError

_SERVICE_RE = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")


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

    async def _get(self, path: str, params: dict | None = None) -> dict:
        try:
            response = await self.http.get(
                f"{self.base_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self.token}"},
            )
        except httpx.HTTPError as exc:
            raise MCPDomainError(
                "control_plane_unavailable",
                "Control plane is unavailable.",
            ) from exc

        if response.status_code >= 500:
            raise MCPDomainError(
                "control_plane_unavailable",
                "Control plane is unavailable.",
            )
        if response.status_code < 400:
            try:
                return response.json()
            except ValueError as exc:
                raise MCPDomainError(
                    "control_plane_unavailable",
                    "Control plane returned an invalid response.",
                ) from exc

        try:
            body = response.json()
        except ValueError:
            body = {}
        code = body.get("error")
        message = body.get("message")

        if response.status_code == 400:
            raise MCPDomainError(
                "invalid_request",
                message or "The request is invalid.",
            )
        if response.status_code in {401, 403}:
            raise MCPDomainError(
                "forbidden",
                "This MCP identity cannot perform this operation.",
            )
        if response.status_code == 404:
            allowed = {"server_not_found", "service_not_found"}
            normalized = code if code in allowed else "server_not_found"
            raise MCPDomainError(
                normalized,
                message or "The requested resource does not exist.",
            )
        if response.status_code == 409:
            allowed = {
                "default_server_not_configured",
                "server_offline",
                "metrics_unavailable",
            }
            normalized = code if code in allowed else "invalid_request"
            safe_message = message or {
                "default_server_not_configured": "Default server is not configured.",
                "server_offline": "Server has not reported recently.",
                "metrics_unavailable": "No metrics snapshot is available.",
            }.get(normalized, "The request cannot be completed.")
            data = {}
            if normalized == "server_offline" and body.get("last_seen_at"):
                data["last_seen_at"] = body["last_seen_at"]
            raise MCPDomainError(normalized, safe_message, data)

        raise MCPDomainError(
            "control_plane_unavailable",
            "Control plane request failed.",
        )

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            response = await self.http.post(
                f"{self.base_url}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
            )
        except httpx.HTTPError as exc:
            raise MCPDomainError(
                "control_plane_unavailable", "Control plane is unavailable."
            ) from exc
        if response.status_code < 400:
            try:
                return response.json()
            except ValueError as exc:
                raise MCPDomainError(
                    "control_plane_unavailable",
                    "Control plane returned an invalid response.",
                ) from exc
        if response.status_code in {401, 403}:
            raise MCPDomainError(
                "forbidden", "This MCP identity cannot perform this operation."
            )
        if response.status_code in {400, 404, 409}:
            raise MCPDomainError("invalid_request", "The operation was rejected.")
        raise MCPDomainError("control_plane_unavailable", "Control plane request failed.")

    @staticmethod
    def _server_id(server_id: str | None) -> str:
        return server_id or "default"

    async def list_servers(self) -> dict:
        return await self._get("/api/control/v1/servers/")

    async def get_server(self, server_id: str | None) -> dict:
        return await self._get(
            f"/api/control/v1/servers/{self._server_id(server_id)}/"
        )

    async def get_metrics(self, server_id: str | None) -> dict:
        return await self._get(
            f"/api/control/v1/servers/{self._server_id(server_id)}/metrics/"
        )

    async def list_services(
        self,
        server_id: str | None,
        status: str | None,
    ) -> dict:
        params = {"status": status} if status else None
        return await self._get(
            f"/api/control/v1/servers/{self._server_id(server_id)}/services/",
            params=params,
        )

    async def get_service(
        self,
        service_name: str,
        server_id: str | None,
    ) -> dict:
        if not _SERVICE_RE.fullmatch(service_name):
            raise MCPDomainError(
                "invalid_request",
                "service_name must be an exact systemd unit name.",
            )
        safe_name = quote(service_name, safe="")
        return await self._get(
            f"/api/control/v1/servers/{self._server_id(server_id)}/services/{safe_name}/"
        )

    async def get_audit(self, server_id: str | None, limit: int) -> dict:
        params = {"limit": max(1, min(limit, 100))}
        if server_id:
            params["server_id"] = server_id
        return await self._get("/api/control/v1/audit/", params=params)

    def _validate_service_name(self, service_name: str) -> None:
        if not _SERVICE_RE.fullmatch(service_name):
            raise MCPDomainError(
                "invalid_request", "service_name must be an exact systemd unit name."
            )

    async def create_service_operation(
        self,
        server_id: str | None,
        action: str,
        service_name: str,
        idempotency_key: str,
    ) -> dict:
        if action not in {"start", "stop", "restart"}:
            raise MCPDomainError("invalid_request", "Unsupported service action.")
        self._validate_service_name(service_name)
        return await self._post(
            "/api/control/v1/operations/",
            {
                "server_id": self._server_id(server_id),
                "kind": f"service.{action}",
                "payload": {"unit_name": service_name},
                "idempotency_key": idempotency_key,
            },
        )

    async def create_logs_operation(
        self,
        server_id: str | None,
        service_name: str,
        lines: int,
        since_seconds: int,
        idempotency_key: str,
    ) -> dict:
        self._validate_service_name(service_name)
        if not 1 <= lines <= 200 or not 60 <= since_seconds <= 86400:
            raise MCPDomainError("invalid_request", "Log bounds are invalid.")
        return await self._post(
            "/api/control/v1/operations/",
            {
                "server_id": self._server_id(server_id),
                "kind": "service.logs",
                "payload": {
                    "unit_name": service_name,
                    "lines": lines,
                    "since_seconds": since_seconds,
                },
                "idempotency_key": idempotency_key,
            },
        )

    async def list_operations(self) -> dict:
        return await self._get("/api/control/v1/operations/")

    async def get_operation(self, operation_id: str) -> dict:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", operation_id):
            raise MCPDomainError("invalid_request", "operation_id must be a UUID.")
        return await self._get(f"/api/control/v1/operations/{operation_id}/")

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()
