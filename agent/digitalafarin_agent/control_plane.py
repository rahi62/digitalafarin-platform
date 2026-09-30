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

    def _agent_headers(self, agent_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {agent_token}"}

    async def claim_operation(self, agent_token: str) -> dict | None:
        try:
            response = await self.http.post(
                f"{self.base_url}/api/agent/v1/operations/claim",
                headers=self._agent_headers(agent_token),
                json={},
            )
            if response.status_code == 204:
                return None
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ControlPlaneError("operation claim failed") from exc

    async def start_operation(
        self, agent_token: str, operation_id: str, claim_token: str
    ) -> None:
        await self._operation_post(
            agent_token,
            operation_id,
            "started",
            {"claim_token": claim_token},
            "operation start failed",
        )

    async def complete_operation(
        self,
        agent_token: str,
        operation_id: str,
        claim_token: str,
        payload: dict,
    ) -> None:
        await self._operation_post(
            agent_token,
            operation_id,
            "complete",
            {"claim_token": claim_token, **payload},
            "operation completion failed",
        )

    async def progress_operation(self, agent_token, operation_id, claim_token, sequence, stage):
        await self._operation_post(agent_token, operation_id, 'progress',
                                   {'claim_token': claim_token, 'sequence': sequence, 'stage': stage},
                                   'operation progress failed')

    async def _operation_post(
        self,
        agent_token: str,
        operation_id: str,
        action: str,
        payload: dict,
        error_message: str,
    ) -> None:
        try:
            response = await self.http.post(
                f"{self.base_url}/api/agent/v1/operations/{operation_id}/{action}",
                headers=self._agent_headers(agent_token),
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ControlPlaneError(error_message) from exc

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()
