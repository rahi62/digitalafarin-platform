import json
from unittest.mock import AsyncMock

import httpx
import pytest
from mcp import Client
from pydantic import ValidationError

from digitalafarin_vps_mcp.control_plane import ControlPlaneClient
from digitalafarin_vps_mcp.coolify import ApplicationCreate, ApplicationSettings, EnvironmentVariable
from digitalafarin_vps_mcp.errors import MCPDomainError
from digitalafarin_vps_mcp.server import create_mcp

CREATE = {"request_id": "11111111-1111-1111-1111-111111111111", "target": "migration", "name": "demo", "git_repository": "https://github.com/example/app.git", "git_branch": "main", "build_pack": "dockerfile", "ports_exposes": [3000]}


@pytest.mark.asyncio
async def test_control_plane_mapping_never_contacts_coolify():
    seen = []
    async def handler(request):
        assert request.url.host == "control"
        assert request.headers["Authorization"] == "Bearer control-token"
        seen.append((request.method, request.url.path, dict(request.url.params), json.loads(request.content) if request.content else None))
        return httpx.Response(200, json={"ok": True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ControlPlaneClient("https://control", "control-token", http=http)
        await client.list_coolify_management_targets()
        await client.list_coolify_environments("project-1")
        await client.create_coolify_application(ApplicationCreate(**CREATE))
        await client.configure_coolify_application("app-1", ApplicationSettings(ports_exposes=[3000]))
        await client.list_coolify_environment_variables("app-1")
        variable = EnvironmentVariable(key="DATABASE_URL", value="SECRET")
        await client.create_coolify_environment_variable("app-1", variable)
        await client.update_coolify_environment_variable("app-1", variable)
        for action in ["deploy", "redeploy", "start", "stop", "restart"]:
            await getattr(client, f"{action}_coolify_application")("app-1")
        await client.list_coolify_deployments("app-1")
        await client.get_coolify_deployment("app-1", "deployment-1")
        await client.get_coolify_deployment_logs("app-1", "deployment-1", 25)
        await client.delete_coolify_application("app-1", "app-1")
    base = "/api/control/v1/coolify/"
    expected = [("GET", "targets/"), ("GET", "projects/project-1/environments/"), ("POST", "applications/"), ("POST", "applications/app-1/configure/"), ("GET", "applications/app-1/environment/"), ("POST", "applications/app-1/environment/create/"), ("POST", "applications/app-1/environment/update/")]
    expected += [("POST", f"applications/app-1/{action}/") for action in ["deploy", "redeploy", "start", "stop", "restart"]]
    expected += [("GET", "applications/app-1/deployments/"), ("GET", "applications/app-1/deployments/deployment-1/"), ("GET", "applications/app-1/deployments/deployment-1/logs/"), ("POST", "applications/app-1/delete/")]
    assert [(method, path) for method, path, _, _ in seen] == [(method, base + suffix) for method, suffix in expected]
    assert seen[2][3] == CREATE
    assert seen[5][3]["value"] == "SECRET"
    assert seen[-2][2] == {"lines": "25"}
    assert seen[-1][3] == {"confirm_application_uuid": "app-1"}
    assert "SECRET" not in repr(variable)


@pytest.mark.asyncio
async def test_all_new_tools_call_typed_control_plane_methods():
    client = AsyncMock(spec=ControlPlaneClient)
    cases = [
        ("coolify_list_management_targets", "list_coolify_management_targets", {}),
        ("coolify_list_environments", "list_coolify_environments", {"project_uuid": "project-1"}),
        ("coolify_create_application", "create_coolify_application", {"application": CREATE}),
        ("coolify_configure_application", "configure_coolify_application", {"application_uuid": "app-1", "settings": {"ports_exposes": [3000]}}),
        ("coolify_list_environment_variables", "list_coolify_environment_variables", {"application_uuid": "app-1"}),
    ]
    cases += [(f"coolify_{action}_environment_variable", f"{action}_coolify_environment_variable", {"application_uuid": "app-1", "variable": {"key": "DATABASE_URL", "value": "SECRET"}}) for action in ["create", "update"]]
    cases += [(f"coolify_{action}_application", f"{action}_coolify_application", {"application_uuid": "app-1"}) for action in ["deploy", "redeploy", "start", "stop", "restart"]]
    cases += [
        ("coolify_list_deployments", "list_coolify_deployments", {"application_uuid": "app-1"}),
        ("coolify_get_deployment", "get_coolify_deployment", {"application_uuid": "app-1", "deployment_uuid": "deployment-1"}),
        ("coolify_get_deployment_logs", "get_coolify_deployment_logs", {"application_uuid": "app-1", "deployment_uuid": "deployment-1", "lines": 10}),
        ("coolify_delete_application", "delete_coolify_application", {"application_uuid": "app-1", "confirm_application_uuid": "app-1"}),
    ]
    async with Client(create_mcp(client), raise_exceptions=True) as mcp:
        for tool, method, args in cases:
            getattr(client, method).return_value = {"ok": True}
            response = await mcp.call_tool(tool, args)
            assert not response.is_error
            getattr(client, method).assert_awaited_once()
    assert isinstance(client.create_coolify_application.call_args.args[0], ApplicationCreate)
    assert isinstance(client.configure_coolify_application.call_args.args[1], ApplicationSettings)
    assert isinstance(client.create_coolify_environment_variable.call_args.args[1], EnvironmentVariable)


@pytest.mark.asyncio
async def test_invalid_ids_and_log_bounds_do_not_make_http_requests():
    async def handler(request):
        pytest.fail("HTTP must not be called")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ControlPlaneClient("https://control", "token", http=http)
        for value in ["../servers", "app/stop", "app?x=1", "a" * 81]:
            with pytest.raises(MCPDomainError):
                await client.stop_coolify_application(value)
        for lines in [0, 201, True, "20"]:
            with pytest.raises(MCPDomainError):
                await client.get_coolify_deployment_logs("app-1", "deployment-1", lines)


@pytest.mark.parametrize("code", [401, 403, 500, 502])
@pytest.mark.asyncio
async def test_coolify_upstream_failures_are_sanitized_at_mcp(code):
    async def handler(request):
        return httpx.Response(code, json={"message": "SECRET"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ControlPlaneClient("https://control", "token", http=http)
        with pytest.raises(MCPDomainError) as error:
            await client.deploy_coolify_application("app-1")
        assert "SECRET" not in str(error.value)


@pytest.mark.parametrize("extra", [{"command": "id"}, {"dockerfile": "FROM scratch"}, {"build_pack": "dockercompose"}, {"ports_exposes": [65536]}])
def test_typed_schema_rejects_execution_fields_and_invalid_settings(extra):
    with pytest.raises(ValidationError):
        ApplicationCreate(**{**CREATE, **extra})


@pytest.mark.asyncio
async def test_mcp_validation_errors_do_not_echo_environment_values():
    client = AsyncMock(spec=ControlPlaneClient)
    async with Client(create_mcp(client)) as mcp:
        for variable in [{"key": "invalid-key", "value": "SECRET-MARKER"}, {"key": "DATABASE_URL", "value": "SECRET-MARKER", "command": "id"}]:
            result = await mcp.call_tool("coolify_create_environment_variable", {"application_uuid": "app-1", "variable": variable})
            assert "SECRET-MARKER" not in str(result)
    client.create_coolify_environment_variable.assert_not_called()
