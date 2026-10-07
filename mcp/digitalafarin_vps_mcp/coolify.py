"""Typed Coolify MCP contracts. All traffic goes through the Control Plane."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$", max_length=80)]
Port = Annotated[int, Field(strict=True, ge=1, le=65535)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ApplicationSettings(Contract):
    git_repository: Annotated[str, Field(max_length=500)] | None = None
    git_branch: Annotated[str, Field(max_length=200)] | None = None
    base_directory: Annotated[str, Field(max_length=200)] | None = None
    build_pack: Literal["nixpacks", "railpack", "static", "dockerfile"] | None = None
    publish_directory: Annotated[str, Field(max_length=200)] | None = None
    ports_exposes: Annotated[list[Port], Field(min_length=1, max_length=16)] | None = None
    domains: Annotated[list[Annotated[str, Field(max_length=253)]], Field(max_length=10)] | None = None
    is_static: bool | None = None
    limits_memory: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,3}[MG]$")] | None = None
    limits_cpus: Annotated[float, Field(ge=0.1, le=64)] | None = None


class ApplicationCreate(ApplicationSettings):
    request_id: Annotated[str, Field(pattern=r"^[0-9a-fA-F-]{36}$")]
    target: Identifier
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")]
    git_repository: Annotated[str, Field(max_length=500)]
    git_branch: Annotated[str, Field(max_length=200)]
    build_pack: Literal["nixpacks", "railpack", "static", "dockerfile"]
    ports_exposes: Annotated[list[Port], Field(min_length=1, max_length=16)]


class EnvironmentVariable(Contract):
    key: Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")]
    value: SecretStr = Field(max_length=16384)
    is_buildtime: bool = False
    is_runtime: bool = True

    def payload(self):
        return {**self.model_dump(exclude={"value"}), "value": self.value.get_secret_value()}


def register_coolify_tools(mcp, client, safe):
    @mcp.tool()
    async def coolify_list_management_targets() -> dict:
        """List administrator-approved target IDs and project/environment/server placement."""
        return await safe(client.list_coolify_management_targets())

    @mcp.tool()
    async def coolify_list_environments(project_uuid: Identifier) -> dict:
        """List environment UUIDs in one Coolify project."""
        return await safe(client.list_coolify_environments(project_uuid))

    @mcp.tool()
    async def coolify_create_application(application: ApplicationCreate) -> dict:
        """Create without deploying in an approved target; request_id prevents duplicate submissions."""
        return await safe(client.create_coolify_application(application))

    @mcp.tool()
    async def coolify_configure_application(application_uuid: Identifier, settings: ApplicationSettings) -> dict:
        """Configure an owned application using allow-listed settings; no commands or raw Docker content."""
        return await safe(client.configure_coolify_application(application_uuid, settings))

    @mcp.tool()
    async def coolify_list_environment_variables(application_uuid: Identifier) -> dict:
        """Read approved variable names and build/runtime flags. Values are never returned."""
        return await safe(client.list_coolify_environment_variables(application_uuid))

    @mcp.tool()
    async def coolify_create_environment_variable(application_uuid: Identifier, variable: EnvironmentVariable) -> dict:
        """Create an approved literal variable; value is write-only and never echoed."""
        return await safe(client.create_coolify_environment_variable(application_uuid, variable))

    @mcp.tool()
    async def coolify_update_environment_variable(application_uuid: Identifier, variable: EnvironmentVariable) -> dict:
        """Replace an approved literal variable; value is write-only and never echoed."""
        return await safe(client.update_coolify_environment_variable(application_uuid, variable))

    @mcp.tool()
    async def coolify_deploy_application(application_uuid: Identifier) -> dict:
        """Queue deployment of an owned application; requires coolify:deploy."""
        return await safe(client.deploy_coolify_application(application_uuid))

    @mcp.tool()
    async def coolify_redeploy_application(application_uuid: Identifier) -> dict:
        """Queue deployment with forced rebuild of an owned application."""
        return await safe(client.redeploy_coolify_application(application_uuid))

    @mcp.tool()
    async def coolify_start_application(application_uuid: Identifier) -> dict:
        """Start via Coolify's deployment queue (may build an image)."""
        return await safe(client.start_coolify_application(application_uuid))

    @mcp.tool()
    async def coolify_stop_application(application_uuid: Identifier) -> dict:
        """Stop an owned application without Docker cleanup."""
        return await safe(client.stop_coolify_application(application_uuid))

    @mcp.tool()
    async def coolify_restart_application(application_uuid: Identifier) -> dict:
        """Queue restart-only deployment of an owned application."""
        return await safe(client.restart_coolify_application(application_uuid))

    @mcp.tool()
    async def coolify_list_deployments(application_uuid: Identifier) -> dict:
        """Read up to 20 recent deployment identifiers and statuses."""
        return await safe(client.list_coolify_deployments(application_uuid))

    @mcp.tool()
    async def coolify_get_deployment(application_uuid: Identifier, deployment_uuid: Identifier) -> dict:
        """Read deployment status after verifying ownership by the given application."""
        return await safe(client.get_coolify_deployment(application_uuid, deployment_uuid))

    @mcp.tool()
    async def coolify_get_deployment_logs(application_uuid: Identifier, deployment_uuid: Identifier, lines: Annotated[int, Field(ge=1, le=200)] = 100) -> dict:
        """Read bounded logs: only exact approved lifecycle messages survive; other output is redacted."""
        return await safe(client.get_coolify_deployment_logs(application_uuid, deployment_uuid, lines))

    @mcp.tool()
    async def coolify_delete_application(application_uuid: Identifier, confirm_application_uuid: Identifier) -> dict:
        """DESTRUCTIVE: delete an owned application with exact UUID confirmation and coolify:delete; preserve volumes/networks."""
        return await safe(client.delete_coolify_application(application_uuid, confirm_application_uuid))
