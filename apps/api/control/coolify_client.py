import json
import os
import re

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

    MAX_RESPONSE_BYTES = 2 * 1024 * 1024

    @staticmethod
    def _identifier(value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
            raise ValueError("Invalid Coolify identifier.")
        return value

    def _request(self, method: str, path: str, *, payload: dict | None = None, params: dict | None = None):
        # No redirects or automatic retries, especially for uncertain writes.
        try:
            with self.http.stream(
                method, f"{self.base_url}/api/v1{path}",
                json=payload, params=params, follow_redirects=False,
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            ) as response:
                if not 200 <= response.status_code < 300:
                    raise CoolifyUpstreamError("Coolify request failed.")
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    content.extend(chunk)
                    if len(content) > self.MAX_RESPONSE_BYTES:
                        raise CoolifyUpstreamError("Coolify response exceeds the size limit.")
        except httpx.HTTPError:
            raise CoolifyUpstreamError("Coolify is unavailable.") from None
        if path == "/version":
            return content.decode("utf-8", errors="replace").strip().strip('"')[:80]
        try:
            return json.loads(content)
        except (ValueError, UnicodeError):
            raise CoolifyUpstreamError("Coolify returned an invalid response.") from None

    def _get(self, path: str):
        return self._request("GET", path)

    def list_environments(self, project_uuid: str) -> list:
        return self._get(f"/projects/{self._identifier(project_uuid)}/environments")

    def get_environment(self, project_uuid: str, environment_uuid: str) -> dict:
        return self._get(f"/projects/{self._identifier(project_uuid)}/{self._identifier(environment_uuid)}")

    def list_server_resources(self, server_uuid: str) -> list:
        return self._get(f"/servers/{self._identifier(server_uuid)}/resources")

    def create_application(self, payload: dict) -> dict:
        return self._request("POST", "/applications/public", payload=payload)

    def create_github_application(self, payload: dict) -> dict:
        return self._request("POST", "/applications/private-github-app", payload=payload)

    def get_application(self, application_uuid: str) -> dict:
        return self._get(f"/applications/{self._identifier(application_uuid)}")

    def update_application(self, application_uuid: str, payload: dict) -> dict:
        return self._request("PATCH", f"/applications/{self._identifier(application_uuid)}", payload=payload)

    def list_environment_variables(self, application_uuid: str) -> list:
        return self._get(f"/applications/{self._identifier(application_uuid)}/envs")

    def create_environment_variable(self, application_uuid: str, payload: dict) -> dict:
        return self._request("POST", f"/applications/{self._identifier(application_uuid)}/envs", payload=payload)

    def update_environment_variable(self, application_uuid: str, payload: dict) -> dict:
        return self._request("PATCH", f"/applications/{self._identifier(application_uuid)}/envs", payload=payload)

    def deploy_application(self, application_uuid: str, *, force: bool = False) -> dict:
        return self._request("POST", f"/applications/{self._identifier(application_uuid)}/start", payload={"force": force, "instant_deploy": False})

    def start_application(self, application_uuid: str) -> dict:
        return self.deploy_application(application_uuid)

    def stop_application(self, application_uuid: str) -> dict:
        return self._request("POST", f"/applications/{self._identifier(application_uuid)}/stop", payload={"docker_cleanup": False})

    def restart_application(self, application_uuid: str) -> dict:
        return self._request("POST", f"/applications/{self._identifier(application_uuid)}/restart", payload={})

    def get_deployment(self, deployment_uuid: str) -> dict:
        return self._get(f"/deployments/{self._identifier(deployment_uuid)}")

    def list_application_deployments(self, application_uuid: str) -> dict:
        return self._request("GET", f"/deployments/applications/{self._identifier(application_uuid)}", params={"skip": 0, "take": 20})

    def delete_application(self, application_uuid: str) -> dict:
        return self._request("DELETE", f"/applications/{self._identifier(application_uuid)}", params={
            "delete_volumes": "false", "delete_connected_networks": "false",
            "delete_configurations": "false", "docker_cleanup": "false",
        })

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
