import os

import httpx


class CoolifyConfigurationError(RuntimeError):
    pass


class CoolifyUpstreamError(RuntimeError):
    pass


class CoolifyClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        http: httpx.Client | None = None,
    ):
        self.base_url = (base_url or os.getenv("COOLIFY_BASE_URL", "")).rstrip("/")
        self.token = token or os.getenv("COOLIFY_API_TOKEN", "")
        if not self.base_url or not self.token:
            raise CoolifyConfigurationError("Coolify integration is not configured.")
        self.http = http or httpx.Client(timeout=10.0)
        self._owns_http = http is None

    def _get(self, path: str):
        try:
            response = self.http.get(
                f"{self.base_url}/api/v1{path}",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise CoolifyUpstreamError("Coolify is unavailable.") from exc

        if response.status_code in {401, 403}:
            raise CoolifyUpstreamError("Coolify rejected the configured credential.")
        if response.status_code >= 400:
            raise CoolifyUpstreamError("Coolify request failed.")
        if path == "/version":
            return response.text.strip().strip('"')
        try:
            return response.json()
        except ValueError as exc:
            raise CoolifyUpstreamError("Coolify returned an invalid response.") from exc

    def version(self):
        return self._get("/version")

    def list_servers(self):
        return self._get("/servers")

    def list_projects(self):
        return self._get("/projects")

    def list_resources(self):
        return self._get("/resources")

    def close(self):
        if self._owns_http:
            self.http.close()
