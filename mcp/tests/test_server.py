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

    async def list_operations(self):
        return {"items": []}

    async def get_operation(self, operation_id):
        return {"id": operation_id, "state": "succeeded"}

    async def list_projects(self):
        return {"items": [{"id": "project-id", "name": "Oily"}]}

    async def get_project(self, project_id):
        return {"id": project_id, "variables": [{"key": "SECRET", "has_value": True}]}

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
