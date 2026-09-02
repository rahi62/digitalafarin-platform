import httpx
import pytest

from digitalafarin_agent.control_plane import AgentControlPlaneClient, ControlPlaneError


@pytest.mark.asyncio
async def test_enroll_uses_enrollment_bearer_and_returns_agent_token():
    async def handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer enroll-token"
        return httpx.Response(
            201,
            json={
                "server_id": "11111111-1111-1111-1111-111111111111",
                "agent_token": "da_agent_p.s",
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AgentControlPlaneClient("https://control.example", http=http)

    result = await client.enroll(
        "enroll-token",
        {
            "name": "VPS",
            "hostname": "host",
            "agent_version": "0.2.0",
            "capabilities": [],
        },
    )

    assert result.agent_token == "da_agent_p.s"
    await http.aclose()


@pytest.mark.asyncio
async def test_heartbeat_error_is_sanitized():
    async def handler(_request: httpx.Request):
        return httpx.Response(401, json={"detail": "secret raw backend response"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AgentControlPlaneClient("https://control.example", http=http)

    with pytest.raises(ControlPlaneError) as exc:
        await client.heartbeat("da_agent_prefix.secret", {"metrics": {}})

    assert str(exc.value) == "agent heartbeat failed"
    assert "secret" not in str(exc.value)
    await http.aclose()
