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


@pytest.mark.asyncio
async def test_create_service_operation_without_server_id_resolves_default_uuid():
    seen = []
    server_id = "11111111-1111-1111-1111-111111111111"

    async def handler(request: httpx.Request):
        seen.append((request.method, request.url.path, request.read().decode()))
        if request.method == "GET":
            return httpx.Response(200, json={"id": server_id})
        return httpx.Response(201, json={"id": "operation-id", "state": "queued"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ControlPlaneClient("http://control", "service-secret", http=http)

    await client.create_service_operation(None, "restart", "oily-api.service", "request-1")

    assert seen[0][1] == "/api/control/v1/servers/default/"
    assert seen[1][1] == "/api/control/v1/operations/"
    assert f'"server_id":"{server_id}"' in seen[1][2]
    await http.aclose()


@pytest.mark.asyncio
async def test_create_bootstrap_operation_posts_empty_typed_payload_with_resolved_server():
    seen = []
    server_id = "11111111-1111-1111-1111-111111111111"

    async def handler(request: httpx.Request):
        seen.append((request.method, request.url.path, request.read().decode()))
        if request.method == "GET":
            return httpx.Response(200, json={"id": server_id})
        return httpx.Response(201, json={"id": "bootstrap-id", "kind": "server.bootstrap", "state": "queued"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ControlPlaneClient("http://control", "service-secret", http=http)

    result = await client.create_bootstrap_operation(None, "bootstrap-1")

    assert result["kind"] == "server.bootstrap"
    assert seen[1][1] == "/api/control/v1/operations/"
    assert '"kind":"server.bootstrap"' in seen[1][2]
    assert '"payload":{}' in seen[1][2]
    assert '"idempotency_key":"bootstrap-1"' in seen[1][2]
    await http.aclose()


@pytest.mark.asyncio
async def test_create_project_posts_only_name_and_slug():
    seen = []

    async def handler(request: httpx.Request):
        seen.append((request.url.path, request.read().decode()))
        return httpx.Response(201, json={"id": "project-id", "name": "Oily", "slug": "oily"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ControlPlaneClient("http://control", "service-secret", http=http)

    result = await client.create_project("Oily", "oily")

    assert result["slug"] == "oily"
    assert seen == [("/api/control/v1/projects/", '{"name":"Oily","slug":"oily"}')]
    await http.aclose()


@pytest.mark.asyncio
async def test_adopt_service_posts_only_narrow_metadata_payload():
    seen = []

    async def handler(request: httpx.Request):
        seen.append((request.url.path, request.read().decode()))
        return httpx.Response(201, json={"id": "service-id", "lifecycle_state": "adopted"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ControlPlaneClient("http://control", "service-secret", http=http)
    result = await client.adopt_service(
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "oily-backend.service",
        "backend",
    )
    assert result["lifecycle_state"] == "adopted"
    assert seen == [(
        "/api/control/v1/projects/11111111-1111-1111-1111-111111111111/services/adopt/",
        '{"server_id":"22222222-2222-2222-2222-222222222222","unit_name":"oily-backend.service","name":"backend"}',
    )]
    await http.aclose()


@pytest.mark.asyncio
async def test_configure_service_deployment_puts_complete_structured_configuration():
    seen = []

    async def handler(request: httpx.Request):
        seen.append((request.method, request.url.path, request.read().decode()))
        return httpx.Response(200, json={"id": "service-id", "lifecycle_state": "configured"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ControlPlaneClient("http://control", "service-secret", http=http)
    result = await client.configure_service_deployment(
        "33333333-3333-3333-3333-333333333333",
        "https://github.com/example/oily.git",
        "main",
        "backend",
        "python-django",
        8000,
        {"requirements_file": "requirements.txt"},
        {"migrate": True, "collectstatic": True, "gunicorn_module": "config.wsgi:application"},
    )
    assert result["lifecycle_state"] == "configured"
    assert seen[0][0] == "PUT"
    assert seen[0][1] == "/api/control/v1/services/33333333-3333-3333-3333-333333333333/deployment-configuration/"
    assert "command" not in seen[0][2]
    assert "unit_file" not in seen[0][2]
    await http.aclose()
