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
