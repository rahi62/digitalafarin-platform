from typing import Any, Awaitable

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
            "Read-only access to DigitalAfarin VPS inventory, health, systemd "
            "services, metrics, and audit events. Do not claim that this server "
            "can mutate VPS state."
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
