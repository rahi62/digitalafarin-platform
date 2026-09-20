import pytest
from mcp import Client

from digitalafarin_vps_mcp.server import create_mcp


class FakeControlPlane:
    async def list_servers(self):
        return {
            "items": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "name": "Primary",
                    "status": "online",
                }
            ]
        }

    async def get_server(self, server_id):
        return {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Primary",
            "status": "online",
        }

    async def get_metrics(self, server_id):
        return {
            "id": "11111111-1111-1111-1111-111111111111",
            "cpu_percent": 10.0,
            "stale": False,
        }

    async def list_services(self, server_id, status):
        return {"items": []}

    async def get_service(self, service_name, server_id):
        return {"unit_name": service_name, "active_state": "active"}

    async def get_audit(self, server_id, limit):
        return {"items": []}

    async def create_service_operation(self, server_id, action, service_name, idempotency_key):
        return {"id": "operation-id", "kind": f"service.{action}", "state": "queued"}

    async def create_logs_operation(self, server_id, service_name, lines, since_seconds, idempotency_key):
        return {"id": "logs-operation-id", "kind": "service.logs", "state": "queued"}

    async def create_bootstrap_operation(self, server_id, idempotency_key):
        return {"id": "bootstrap-operation-id", "kind": "server.bootstrap", "state": "queued"}

    async def list_operations(self):
        return {"items": []}

    async def get_operation(self, operation_id):
        return {"id": operation_id, "state": "succeeded"}

    async def list_projects(self):
        return {"items": [{"id": "project-id", "name": "Oily"}]}

    async def create_project(self, name, slug):
        return {"id": "project-id", "name": name, "slug": slug}

    async def get_project(self, project_id):
        return {"id": project_id, "variables": [{"key": "SECRET", "has_value": True}]}

    async def adopt_service(self, project_id, server_id, unit_name, name):
        return {"id": "service-id", "unit_name": unit_name, "name": name, "lifecycle_state": "adopted"}

    async def configure_service_deployment(
        self, service_id, repository, branch, root_directory, runtime, service_port,
        install_configuration, build_configuration,
    ):
        return {"id": service_id, "lifecycle_state": "configured"}

    async def prepare_service_takeover(self, service_id, commit):
        return {
            "id": "takeover-id",
            "service_id": service_id,
            "requested_commit": commit,
            "state": "queued",
        }

    async def get_service_takeover(self, takeover_id):
        return {"id": takeover_id, "state": "prepared"}

    async def activate_service_takeover(self, takeover_id):
        return {"id": takeover_id, "state": "prepared", "activate_operation_id": "operation-id"}

    async def cancel_service_takeover(self, takeover_id):
        return {"id": takeover_id, "state": "canceled"}

    async def deploy_service(self, service_id, commit):
        return {"id": "deployment-id", "state": "queued"}

    async def get_deployment(self, deployment_id):
        return {"id": deployment_id, "state": "succeeded"}

    async def redeploy(self, deployment_id):
        return {"id": "redeployment-id", "state": "queued"}

    async def rollback(self, deployment_id):
        return {"id": "rollback-id", "state": "queued"}


@pytest.mark.asyncio
async def test_server_discovers_only_inventory_and_typed_operation_tools():
    server = create_mcp(FakeControlPlane())
    async with Client(server, raise_exceptions=True) as client:
        result = await client.list_tools()
        names = {tool.name for tool in result.tools}

    assert names == {
        "vps_list_servers",
        "vps_get_server",
        "vps_get_metrics",
        "vps_list_services",
        "vps_get_service",
        "vps_get_recent_audit_events",
        "vps_create_service_operation",
        "vps_create_service_logs_operation",
        "vps_list_operations",
        "vps_get_operation",
        "vps_list_projects",
        "vps_get_project",
        "vps_create_bootstrap_operation",
        "vps_create_project",
        "vps_adopt_service",
        "vps_configure_service_deployment",
        "vps_prepare_service_takeover",
        "vps_get_service_takeover",
        "vps_activate_service_takeover",
        "vps_cancel_service_takeover",
        "vps_deploy_service",
        "vps_get_deployment",
        "vps_redeploy_deployment",
        "vps_rollback_deployment",
    }


@pytest.mark.asyncio
async def test_typed_service_operation_tool_accepts_only_declared_action():
    server = create_mcp(FakeControlPlane())
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool(
            "vps_create_service_operation",
            {
                "action": "restart",
                "service_name": "oily-api.service",
                "server_id": "11111111-1111-1111-1111-111111111111",
            },
        )

    assert result.structured_content["kind"] == "service.restart"


@pytest.mark.asyncio
async def test_project_tool_returns_secret_metadata_only():
    server = create_mcp(FakeControlPlane())
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool("vps_get_project", {"project_id": "project-id"})

    assert result.structured_content["variables"] == [{"key": "SECRET", "has_value": True}]
    assert "sentinel-secret" not in str(result)


@pytest.mark.asyncio
async def test_adoption_tool_returns_adopted_service_metadata():
    server = create_mcp(FakeControlPlane())
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool(
            "vps_adopt_service",
            {
                "project_id": "11111111-1111-1111-1111-111111111111",
                "server_id": "22222222-2222-2222-2222-222222222222",
                "unit_name": "oily-backend.service",
                "name": "backend",
            },
        )
    assert result.structured_content["lifecycle_state"] == "adopted"


@pytest.mark.asyncio
async def test_configuration_tool_returns_configured_service_metadata():
    server = create_mcp(FakeControlPlane())
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool(
            "vps_configure_service_deployment",
            {
                "service_id": "33333333-3333-3333-3333-333333333333",
                "repository": "https://github.com/example/oily.git",
                "branch": "main",
                "root_directory": "backend",
                "runtime": "python-django",
                "service_port": 8000,
                "install_configuration": {"requirements_file": "requirements.txt"},
                "build_configuration": {"migrate": True},
            },
        )
    assert result.structured_content["lifecycle_state"] == "configured"


@pytest.mark.asyncio
async def test_takeover_tools_expose_only_typed_identity_inputs():
    server = create_mcp(FakeControlPlane())
    async with Client(server, raise_exceptions=True) as client:
        prepared = await client.call_tool(
            "vps_prepare_service_takeover",
            {
                "service_id": "33333333-3333-3333-3333-333333333333",
                "commit": "a" * 40,
            },
        )
        read = await client.call_tool(
            "vps_get_service_takeover",
            {"takeover_id": "22222222-2222-2222-2222-222222222222"},
        )
        activated = await client.call_tool(
            "vps_activate_service_takeover",
            {"takeover_id": "22222222-2222-2222-2222-222222222222"},
        )
        canceled = await client.call_tool(
            "vps_cancel_service_takeover",
            {"takeover_id": "22222222-2222-2222-2222-222222222222"},
        )

    assert prepared.structured_content["state"] == "queued"
    assert read.structured_content["state"] == "prepared"
    assert activated.structured_content["activate_operation_id"] == "operation-id"
    assert canceled.structured_content["state"] == "canceled"
