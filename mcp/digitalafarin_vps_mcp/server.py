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
    async def coolify_get_status() -> dict[str, Any]:
        """Read the configured Coolify instance version through the control plane."""
        return await _safe(client.get_coolify_status())

    @mcp.tool()
    async def coolify_list_servers() -> dict[str, Any]:
        """List Coolify servers without sensitive values."""
        return await _safe(client.list_coolify_servers())

    @mcp.tool()
    async def coolify_list_projects() -> dict[str, Any]:
        """List Coolify projects without secret values."""
        return await _safe(client.list_coolify_projects())

    @mcp.tool()
    async def coolify_list_resources() -> dict[str, Any]:
        """List Coolify resources without requesting sensitive values."""
        return await _safe(client.list_coolify_resources())

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
    async def vps_create_bootstrap_operation(
        server_id: str | None = None,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Queue the fixed typed server bootstrap operation; no caller commands or paths."""
        return await _safe(client.create_bootstrap_operation(server_id, idempotency_key))

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
    async def vps_create_project(name: str, slug: str) -> dict[str, Any]:
        """Create one migration project using only validated name and slug metadata."""
        return await _safe(client.create_project(name, slug))

    @mcp.tool()
    async def vps_get_project(project_id: str) -> dict[str, Any]:
        """Get project services and secret-free resource metadata."""
        return await _safe(client.get_project(project_id))

    @mcp.tool()
    async def vps_create_service(
        project_id: str,
        name: str,
        repository: str,
        branch: str,
        root_directory: str,
        runtime: Literal["node-nextjs", "python-django"],
        service_port: int,
        target_server_id: str,
        install_configuration: dict[str, Any],
        build_configuration: dict[str, Any],
    ) -> dict[str, Any]:
        """Create one managed systemd service with validated deployment metadata."""
        return await _safe(
            client.create_service(
                project_id,
                name,
                repository,
                branch,
                root_directory,
                runtime,
                service_port,
                target_server_id,
                install_configuration,
                build_configuration,
            )
        )

    @mcp.tool()
    async def vps_adopt_service(
        project_id: str,
        server_id: str,
        unit_name: str,
        name: str,
    ) -> dict[str, Any]:
        """Adopt one existing inventory systemd unit as metadata only; no workload operation is queued."""
        return await _safe(
            client.adopt_service(project_id, server_id, unit_name, name)
        )

    @mcp.tool()
    async def vps_configure_service_deployment(
        service_id: str,
        repository: str,
        branch: str,
        root_directory: str,
        runtime: Literal["node-nextjs", "python-django"],
        service_port: int,
        install_configuration: dict[str, Any],
        build_configuration: dict[str, Any],
    ) -> dict[str, Any]:
        """Store validated deployment metadata for an adopted service without enabling management."""
        return await _safe(
            client.configure_service_deployment(
                service_id,
                repository,
                branch,
                root_directory,
                runtime,
                service_port,
                install_configuration,
                build_configuration,
            )
        )

    @mcp.tool()
    async def vps_prepare_service_takeover(
        service_id: str,
        commit: str,
    ) -> dict[str, Any]:
        """Prepare an exact-commit controlled takeover without mutating or restarting the service."""
        return await _safe(client.prepare_service_takeover(service_id, commit))

    @mcp.tool()
    async def vps_get_service_takeover(
        takeover_id: str,
    ) -> dict[str, Any]:
        """Read one non-secret controlled takeover record."""
        return await _safe(client.get_service_takeover(takeover_id))

    @mcp.tool()
    async def vps_activate_service_takeover(
        takeover_id: str,
    ) -> dict[str, Any]:
        """Activate one prepared takeover using server-derived execution metadata."""
        return await _safe(client.activate_service_takeover(takeover_id))

    @mcp.tool()
    async def vps_cancel_service_takeover(
        takeover_id: str,
    ) -> dict[str, Any]:
        """Cancel one prepared takeover before activation."""
        return await _safe(client.cancel_service_takeover(takeover_id))

    @mcp.tool()
    async def vps_create_domain(
        project_id: str,
        service_id: str,
        hostname: str,
        configure_nginx: bool = True,
        ssl_enabled: bool = False,
    ) -> dict[str, Any]:
        """Register one validated hostname; optionally keep Nginx externally managed."""
        return await _safe(
            client.create_domain(
                project_id,
                service_id,
                hostname,
                configure_nginx,
                ssl_enabled,
            )
        )

    @mcp.tool()
    async def vps_enable_domain_ssl(domain_id: str) -> dict[str, Any]:
        """Queue TLS enablement for one registered project domain."""
        return await _safe(client.enable_domain_ssl(domain_id))

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
