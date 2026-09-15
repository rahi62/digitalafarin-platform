import httpx
import pytest

from digitalafarin_vps_mcp.control_plane import ControlPlaneClient
from digitalafarin_vps_mcp.errors import MCPDomainError


@pytest.mark.asyncio
async def test_404_is_normalized_without_raw_response_body():
    async def handler(_request: httpx.Request):
        return httpx.Response(
            404,
            json={
                "error": "server_not_found",
                "message": "The requested server does not exist.",
                "debug": "raw-secret-should-never-surface",
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ControlPlaneClient("http://control", "service-secret", http=http)

    with pytest.raises(MCPDomainError) as exc:
        await client.get_server("bad")

    assert exc.value.code == "server_not_found"
    assert "raw-secret" not in str(exc.value)
    assert "traceback" not in str(exc.value).lower()
    await http.aclose()


@pytest.mark.asyncio
async def test_service_name_must_be_exact_systemd_unit():
    client = ControlPlaneClient("http://control", "service-secret")

    with pytest.raises(MCPDomainError) as exc:
        await client.get_service("api.service; shutdown -h now", None)

    assert exc.value.code == "invalid_request"
    await client.close()


@pytest.mark.asyncio
async def test_default_server_identifier_is_used_when_server_id_omitted():
    seen = []

    async def handler(request: httpx.Request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"id": "server-id"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ControlPlaneClient("http://control", "service-secret", http=http)

    await client.get_server(None)

    assert seen == ["/api/control/v1/servers/default/"]
    await http.aclose()


@pytest.mark.asyncio
async def test_create_service_operation_posts_strict_typed_payload():
    seen = []

    async def handler(request: httpx.Request):
        seen.append((request.url.path, request.read().decode()))
        return httpx.Response(201, json={"id": "operation-id", "state": "queued"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ControlPlaneClient("http://control", "service-secret", http=http)

    result = await client.create_service_operation(
        "server-id", "restart", "oily-api.service", "request-1"
    )

    assert result["state"] == "queued"
    assert seen[0][0] == "/api/control/v1/operations/"
    assert '"kind":"service.restart"' in seen[0][1]
    assert '"unit_name":"oily-api.service"' in seen[0][1]
    await http.aclose()


@pytest.mark.asyncio
async def test_create_service_operation_rejects_unknown_action_before_http():
    client = ControlPlaneClient("http://control", "service-secret")

    with pytest.raises(MCPDomainError) as exc:
        await client.create_service_operation(None, "reload", "oily-api.service", "")

    assert exc.value.code == "invalid_request"
    await client.close()
