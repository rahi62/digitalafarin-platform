from dataclasses import dataclass

import httpx


class ControlPlaneError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnrollmentResponse:
    server_id: str
    agent_token: str


class AgentControlPlaneClient:
    def __init__(self, base_url: str, http: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http is None

    async def enroll(self, enrollment_token: str, payload: dict) -> EnrollmentResponse:
        try:
            response = await self.http.post(
                f"{self.base_url}/api/agent/v1/enroll",
                headers={"Authorization": f"Bearer {enrollment_token}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return EnrollmentResponse(
                server_id=data["server_id"],
                agent_token=data["agent_token"],
            )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ControlPlaneError("agent enrollment failed") from exc

    async def heartbeat(self, agent_token: str, payload: dict) -> None:
        try:
            response = await self.http.post(
                f"{self.base_url}/api/agent/v1/heartbeat",
                headers={"Authorization": f"Bearer {agent_token}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ControlPlaneError("agent heartbeat failed") from exc

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()
