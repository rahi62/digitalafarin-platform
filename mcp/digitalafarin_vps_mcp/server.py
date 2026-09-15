from typing import Any, Awaitable, Literal

from mcp.server import MCPServer

from digitalafarin_vps_mcp.config import get_settings
from digitalafarin_vps_mcp.control_plane import ControlPlaneClient
from digitalafarin_vps_mcp.errors import MCPDomainError


async def _safe(call: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    try:
        return await call
    except MCPDomainError as exc:
        return exc.as_dict()


def create_mcp(control_plane: ControlPlaneClient | Any | None = None) -> MCPServer:
    settings = get_settings() if control_plane is None else None
    client = control_plane or ControlPlaneClient(
        settings.control_plane_url,
        settings.control_plane_token,
    )

    mcp = MCPServer(
        "DigitalAfarin VPS",
        instructions=(
            "Inventory reads and strictly typed DigitalAfarin VPS operations. "
            "No arbitrary shell, command, systemctl, filesystem, or SQL access."
        ),
    )

    @mcp.tool()
    async def vps_list_servers() -> dict[str, Any]:
        """List VPS servers visible to this read-only MCP identity."""
        return await _safe(client.list_servers())

    @mcp.tool()
    async def vps_get_server(server_id: str | None = None) -> dict[str, Any]:
        """Get one VPS by UUID, or the configured default VPS when omitted."""
        return await _safe(client.get_server(server_id))

    @mcp.tool()
    async def vps_get_metrics(server_id: str | None = None) -> dict[str, Any]:
        """Get the latest CPU, memory, disk, uptime, and freshness snapshot."""
        return await _safe(client.get_metrics(server_id))

    @mcp.tool()
    async def vps_list_services(
        server_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """List allow-listed systemd services for one VPS."""
        return await _safe(client.list_services(server_id, status))

    @mcp.tool()
    async def vps_get_service(
        service_name: str,
        server_id: str | None = None,
    ) -> dict[str, Any]:
        """Get one allow-listed systemd service by exact unit name."""
        return await _safe(client.get_service(service_name, server_id))

    @mcp.tool()
    async def vps_get_recent_audit_events(
        server_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Read recent platform audit events, optionally scoped to one VPS."""
        return await _safe(client.get_audit(server_id, limit))

    @mcp.tool()
    async def vps_create_service_operation(
        action: Literal["start", "stop", "restart"],
        service_name: str,
        server_id: str | None = None,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Queue one typed action for an exact managed, non-protected service."""
        return await _safe(
            client.create_service_operation(
                server_id, action, service_name, idempotency_key
            )
        )

    @mcp.tool()
    async def vps_create_service_logs_operation(
        service_name: str,
        server_id: str | None = None,
        lines: int = 100,
        since_seconds: int = 3600,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Queue a bounded redacted journal read for one managed service."""
        return await _safe(
            client.create_logs_operation(
                server_id, service_name, lines, since_seconds, idempotency_key
            )
        )

    @mcp.tool()
    async def vps_list_operations() -> dict[str, Any]:
        """List recent typed VPS operations visible to this identity."""
        return await _safe(client.list_operations())

    @mcp.tool()
    async def vps_get_operation(operation_id: str) -> dict[str, Any]:
        """Get one typed operation and any scope-authorized redacted result."""
        return await _safe(client.get_operation(operation_id))

    @mcp.tool()
    async def vps_list_projects() -> dict[str, Any]:
        """List migration projects without secret values."""
        return await _safe(client.list_projects())

    @mcp.tool()
    async def vps_get_project(project_id: str) -> dict[str, Any]:
        """Get project services and secret-free resource metadata."""
        return await _safe(client.get_project(project_id))

    @mcp.tool()
    async def vps_deploy_service(
        service_id: str, commit: str | None = None
    ) -> dict[str, Any]:
        """Queue deploy-latest or an exact lowercase 40-character Git commit."""
        return await _safe(client.deploy_service(service_id, commit))

    @mcp.tool()
    async def vps_get_deployment(deployment_id: str) -> dict[str, Any]:
        """Get deployment state, releases, and redacted events."""
        return await _safe(client.get_deployment(deployment_id))

    @mcp.tool()
    async def vps_redeploy_deployment(deployment_id: str) -> dict[str, Any]:
        """Queue a new deployment of the same exact commit."""
        return await _safe(client.redeploy(deployment_id))

    @mcp.tool()
    async def vps_rollback_deployment(deployment_id: str) -> dict[str, Any]:
        """Queue activation of an existing retained release without rebuilding."""
        return await _safe(client.rollback(deployment_id))

    return mcp


def main() -> None:
    settings = get_settings()
    mcp = create_mcp()
    mcp.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path=settings.mcp_path,
    )


if __name__ == "__main__":
    main()
