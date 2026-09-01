import os

import httpx


class AgentClientError(RuntimeError):
    pass


class AgentClient:
    def __init__(self, base_url: str):
        token = os.getenv("PLATFORM_AGENT_TOKEN", "")
        if not token:
            raise AgentClientError("PLATFORM_AGENT_TOKEN is not configured")
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}

    def snapshot(self) -> tuple[dict, list[dict]]:
        try:
            with httpx.Client(timeout=8.0, headers=self.headers) as client:
                metrics_response = client.get(f"{self.base_url}/v1/metrics")
                services_response = client.get(f"{self.base_url}/v1/services")
                metrics_response.raise_for_status()
                services_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AgentClientError(f"Agent request failed: {exc}") from exc

        metrics = metrics_response.json()
        services = services_response.json().get("items", [])
        return metrics, services
