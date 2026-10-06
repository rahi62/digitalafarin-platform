import re
from urllib.parse import quote

import httpx

from digitalafarin_vps_mcp.errors import MCPDomainError
from digitalafarin_vps_mcp.coolify import ApplicationCreate, ApplicationSettings, EnvironmentVariable

_SERVICE_RE = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
EXACT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

TAKEOVER_ERROR_CODES = {
    "service_not_configured",
    "unsupported_takeover_runtime",
    "inventory_unit_missing",
    "server_offline",
    "disk_usage_blocked",
    "invalid_exact_commit",
    "takeover_already_active",
    "takeover_not_prepared",
    "takeover_already_terminal",
    "takeover_not_found",
    "source_user_unsafe",
    "service_configuration_changed",
    "managed_dropin_conflict",
    "release_prepare_failed",
    "release_validation_failed",
    "takeover_activation_failed",
    "takeover_health_failed",
    "takeover_rollback_failed",
}


def _validate_uuid(value: str, field: str) -> None:
    if not UUID_RE.fullmatch(value):
        raise MCPDomainError("invalid_request", f"{field} must be a UUID.")


class ControlPlaneClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        http: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.http = http or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http is None

    async def _get(self, path: str, params: dict | None = None) -> dict:
        # Management reads/writes perform several bounded upstream checks.
        options = {"timeout": 60.0} if path.startswith("/api/control/v1/coolify/") else {}
        try:
            response = await self.http.get(
                f"{self.base_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self.token}"},
                **options,
            )
        except httpx.HTTPError as exc:
            raise MCPDomainError(
                "control_plane_unavailable",
                "Control plane is unavailable.",
            ) from exc

        if response.status_code >= 500:
            raise MCPDomainError(
                "control_plane_unavailable",
                "Control plane is unavailable.",
            )
        if response.status_code < 400:
            try:
                return response.json()
            except ValueError as exc:
                raise MCPDomainError(
                    "control_plane_unavailable",
                    "Control plane returned an invalid response.",
                ) from exc

        try:
            body = response.json()
        except ValueError:
            body = {}
        code = body.get("error")
        message = body.get("message")

        if response.status_code == 400:
            raise MCPDomainError(
                "invalid_request",
                message or "The request is invalid.",
            )
        if response.status_code in {401, 403}:
            raise MCPDomainError(
                "forbidden",
                "This MCP identity cannot perform this operation.",
            )
        if response.status_code == 404:
            allowed = {"server_not_found", "service_not_found"}
            normalized = code if code in allowed else "server_not_found"
            raise MCPDomainError(
                normalized,
                message or "The requested resource does not exist.",
            )
        if response.status_code == 409:
            allowed = {
                "default_server_not_configured",
                "server_offline",
                "metrics_unavailable",
            }
            normalized = code if code in allowed else "invalid_request"
            safe_message = message or {
                "default_server_not_configured": "Default server is not configured.",
                "server_offline": "Server has not reported recently.",
                "metrics_unavailable": "No metrics snapshot is available.",
            }.get(normalized, "The request cannot be completed.")
            data = {}
            if normalized == "server_offline" and body.get("last_seen_at"):
                data["last_seen_at"] = body["last_seen_at"]
            raise MCPDomainError(normalized, safe_message, data)

        raise MCPDomainError(
            "control_plane_unavailable",
            "Control plane request failed.",
        )

    async def _post(self, path: str, payload: dict) -> dict:
        options = {"timeout": 60.0} if path.startswith("/api/control/v1/coolify/") else {}
        try:
            response = await self.http.post(
                f"{self.base_url}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
                **options,
            )
        except httpx.HTTPError as exc:
            raise MCPDomainError(
                "control_plane_unavailable", "Control plane is unavailable."
            ) from exc
        if response.status_code < 400:
            try:
                return response.json()
            except ValueError as exc:
                raise MCPDomainError(
                    "control_plane_unavailable",
                    "Control plane returned an invalid response.",
                ) from exc
        if response.status_code in {401, 403}:
            raise MCPDomainError(
                "forbidden", "This MCP identity cannot perform this operation."
            )
        if response.status_code in {400, 404, 409}:
            try:
                body = response.json()
            except ValueError:
                body = {}
            code = body.get("error")
            message = body.get("message")
            normalized = code if code in TAKEOVER_ERROR_CODES else "invalid_request"
            raise MCPDomainError(
                normalized,
                message or "The operation was rejected.",
            )
        raise MCPDomainError("control_plane_unavailable", "Control plane request failed.")

    async def _put(self, path: str, payload: dict) -> dict:
        try:
            response = await self.http.put(
                f"{self.base_url}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
            )
        except httpx.HTTPError as exc:
            raise MCPDomainError(
                "control_plane_unavailable", "Control plane is unavailable."
            ) from exc
        if response.status_code < 400:
            try:
                return response.json()
            except ValueError as exc:
                raise MCPDomainError(
                    "control_plane_unavailable",
                    "Control plane returned an invalid response.",
                ) from exc
        if response.status_code in {401, 403}:
            raise MCPDomainError(
                "forbidden", "This MCP identity cannot perform this operation."
            )
        if response.status_code in {400, 404, 409}:
            raise MCPDomainError("invalid_request", "The operation was rejected.")
        raise MCPDomainError(
            "control_plane_unavailable", "Control plane request failed."
        )

    @staticmethod
    def _server_id(server_id: str | None) -> str:
        return server_id or "default"

    async def _mutation_server_id(self, server_id: str | None) -> str:
        if server_id:
            return server_id
        server = await self.get_server(None)
        resolved = server.get("id")
        if not isinstance(resolved, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", resolved):
            raise MCPDomainError(
                "control_plane_unavailable",
                "Control plane returned an invalid default server identity.",
            )
        return resolved

    async def get_coolify_status(self) -> dict:
        return await self._get("/api/control/v1/coolify/status/")

    async def list_coolify_servers(self) -> dict:
        return await self._get("/api/control/v1/coolify/servers/")

    async def list_coolify_projects(self) -> dict:
        return await self._get("/api/control/v1/coolify/projects/")

    async def list_coolify_resources(self) -> dict:
        return await self._get("/api/control/v1/coolify/resources/")

    @staticmethod
    def _coolify_id(value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
            raise MCPDomainError("invalid_request", "Invalid Coolify identifier.")
        return value

    async def list_coolify_management_targets(self) -> dict:
        return await self._get("/api/control/v1/coolify/targets/")

    async def list_coolify_environments(self, project_uuid: str) -> dict:
        return await self._get(f"/api/control/v1/coolify/projects/{self._coolify_id(project_uuid)}/environments/")

    async def create_coolify_application(self, application: ApplicationCreate) -> dict:
        return await self._post("/api/control/v1/coolify/applications/", application.model_dump(exclude_none=True))

    async def configure_coolify_application(self, application_uuid: str, settings: ApplicationSettings) -> dict:
        return await self._post(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/configure/", settings.model_dump(exclude_none=True))

    async def list_coolify_environment_variables(self, application_uuid: str) -> dict:
        return await self._get(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/environment/")

    async def create_coolify_environment_variable(self, application_uuid: str, variable: EnvironmentVariable) -> dict:
        return await self._post(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/environment/create/", variable.payload())

    async def update_coolify_environment_variable(self, application_uuid: str, variable: EnvironmentVariable) -> dict:
        return await self._post(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/environment/update/", variable.payload())

    async def deploy_coolify_application(self, application_uuid: str) -> dict:
        return await self._post(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/deploy/", {})

    async def redeploy_coolify_application(self, application_uuid: str) -> dict:
        return await self._post(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/redeploy/", {})

    async def start_coolify_application(self, application_uuid: str) -> dict:
        return await self._post(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/start/", {})

    async def stop_coolify_application(self, application_uuid: str) -> dict:
        return await self._post(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/stop/", {})

    async def restart_coolify_application(self, application_uuid: str) -> dict:
        return await self._post(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/restart/", {})

    async def list_coolify_deployments(self, application_uuid: str) -> dict:
        return await self._get(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/deployments/")

    async def get_coolify_deployment(self, application_uuid: str, deployment_uuid: str) -> dict:
        return await self._get(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/deployments/{self._coolify_id(deployment_uuid)}/")

    async def get_coolify_deployment_logs(self, application_uuid: str, deployment_uuid: str, lines: int = 100) -> dict:
        if type(lines) is not int or not 1 <= lines <= 200:
            raise MCPDomainError("invalid_request", "lines must be between 1 and 200.")
        return await self._get(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/deployments/{self._coolify_id(deployment_uuid)}/logs/", params={"lines": lines})

    async def delete_coolify_application(self, application_uuid: str, confirm_application_uuid: str) -> dict:
        self._coolify_id(confirm_application_uuid)
        return await self._post(f"/api/control/v1/coolify/applications/{self._coolify_id(application_uuid)}/delete/", {"confirm_application_uuid": confirm_application_uuid})

    async def list_servers(self) -> dict:
        return await self._get("/api/control/v1/servers/")

    async def get_server(self, server_id: str | None) -> dict:
        return await self._get(
            f"/api/control/v1/servers/{self._server_id(server_id)}/"
        )

    async def get_metrics(self, server_id: str | None) -> dict:
        return await self._get(
            f"/api/control/v1/servers/{self._server_id(server_id)}/metrics/"
        )

    async def list_services(
        self,
        server_id: str | None,
        status: str | None,
    ) -> dict:
        params = {"status": status} if status else None
        return await self._get(
            f"/api/control/v1/servers/{self._server_id(server_id)}/services/",
            params=params,
        )

    async def get_service(
        self,
        service_name: str,
        server_id: str | None,
    ) -> dict:
        if not _SERVICE_RE.fullmatch(service_name):
            raise MCPDomainError(
                "invalid_request",
                "service_name must be an exact systemd unit name.",
            )
        safe_name = quote(service_name, safe="")
        return await self._get(
            f"/api/control/v1/servers/{self._server_id(server_id)}/services/{safe_name}/"
        )

    async def get_audit(self, server_id: str | None, limit: int) -> dict:
        params = {"limit": max(1, min(limit, 100))}
        if server_id:
            params["server_id"] = server_id
        return await self._get("/api/control/v1/audit/", params=params)

    def _validate_service_name(self, service_name: str) -> None:
        if not _SERVICE_RE.fullmatch(service_name):
            raise MCPDomainError(
                "invalid_request", "service_name must be an exact systemd unit name."
            )

    async def create_service_operation(
        self,
        server_id: str | None,
        action: str,
        service_name: str,
        idempotency_key: str,
    ) -> dict:
        if action not in {"start", "stop", "restart"}:
            raise MCPDomainError("invalid_request", "Unsupported service action.")
        self._validate_service_name(service_name)
        resolved_server_id = await self._mutation_server_id(server_id)
        return await self._post(
            "/api/control/v1/operations/",
            {
                "server_id": resolved_server_id,
                "kind": f"service.{action}",
                "payload": {"unit_name": service_name},
                "idempotency_key": idempotency_key,
            },
        )

    async def create_logs_operation(
        self,
        server_id: str | None,
        service_name: str,
        lines: int,
        since_seconds: int,
        idempotency_key: str,
    ) -> dict:
        self._validate_service_name(service_name)
        if not 1 <= lines <= 200 or not 60 <= since_seconds <= 86400:
            raise MCPDomainError("invalid_request", "Log bounds are invalid.")
        resolved_server_id = await self._mutation_server_id(server_id)
        return await self._post(
            "/api/control/v1/operations/",
            {
                "server_id": resolved_server_id,
                "kind": "service.logs",
                "payload": {
                    "unit_name": service_name,
                    "lines": lines,
                    "since_seconds": since_seconds,
                },
                "idempotency_key": idempotency_key,
            },
        )


    async def create_bootstrap_operation(
        self,
        server_id: str | None,
        idempotency_key: str,
    ) -> dict:
        resolved_server_id = await self._mutation_server_id(server_id)
        return await self._post(
            "/api/control/v1/operations/",
            {
                "server_id": resolved_server_id,
                "kind": "server.bootstrap",
                "payload": {},
                "idempotency_key": idempotency_key,
            },
        )

    async def list_operations(self) -> dict:
        return await self._get("/api/control/v1/operations/")

    async def get_operation(self, operation_id: str) -> dict:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", operation_id):
            raise MCPDomainError("invalid_request", "operation_id must be a UUID.")
        return await self._get(f"/api/control/v1/operations/{operation_id}/")

    async def list_projects(self) -> dict:
        return await self._get("/api/control/v1/projects/")


    async def create_project(self, name: str, slug: str) -> dict:
        return await self._post(
            "/api/control/v1/projects/",
            {"name": name, "slug": slug},
        )

    async def get_project(self, project_id: str) -> dict:
        return await self._get(f"/api/control/v1/projects/{quote(project_id, safe='')}/")

    async def create_service(
        self,
        project_id: str,
        name: str,
        repository: str,
        branch: str,
        root_directory: str,
        runtime: str,
        service_port: int,
        target_server_id: str,
        install_configuration: dict,
        build_configuration: dict,
    ) -> dict:
        _validate_uuid(project_id, "project_id")
        _validate_uuid(target_server_id, "target_server_id")
        if not SLUG_RE.fullmatch(name):
            raise MCPDomainError(
                "invalid_request", "name must be a safe service slug."
            )
        if runtime not in {"node-nextjs", "python-django"}:
            raise MCPDomainError("invalid_request", "runtime is unsupported.")
        if not 1 <= service_port <= 65535:
            raise MCPDomainError("invalid_request", "service_port is invalid.")
        return await self._post(
            f"/api/control/v1/projects/{quote(project_id, safe='')}/services/",
            {
                "name": name,
                "executor": "systemd",
                "repository": repository,
                "branch": branch,
                "root_directory": root_directory,
                "runtime": runtime,
                "install_configuration": install_configuration,
                "build_configuration": build_configuration,
                "service_port": service_port,
                "target_server_id": target_server_id,
            },
        )

    async def adopt_service(
        self, project_id: str, server_id: str, unit_name: str, name: str
    ) -> dict:
        _validate_uuid(project_id, "project_id")
        _validate_uuid(server_id, "server_id")
        self._validate_service_name(unit_name)
        if not SLUG_RE.fullmatch(name):
            raise MCPDomainError(
                "invalid_request", "name must be a safe service slug."
            )
        return await self._post(
            f"/api/control/v1/projects/{quote(project_id, safe='')}/services/adopt/",
            {"server_id": server_id, "unit_name": unit_name, "name": name},
        )

    async def configure_service_deployment(
        self,
        service_id: str,
        repository: str,
        branch: str,
        root_directory: str,
        runtime: str,
        service_port: int,
        install_configuration: dict,
        build_configuration: dict,
    ) -> dict:
        _validate_uuid(service_id, "service_id")
        if runtime not in {"node-nextjs", "python-django"}:
            raise MCPDomainError("invalid_request", "runtime is unsupported.")
        if not 1 <= service_port <= 65535:
            raise MCPDomainError("invalid_request", "service_port is invalid.")
        return await self._put(
            f"/api/control/v1/services/{quote(service_id, safe='')}/deployment-configuration/",
            {
                "repository": repository,
                "branch": branch,
                "root_directory": root_directory,
                "runtime": runtime,
                "service_port": service_port,
                "install_configuration": install_configuration,
                "build_configuration": build_configuration,
            },
        )

    async def prepare_service_takeover(
        self, service_id: str, commit: str
    ) -> dict:
        _validate_uuid(service_id, "service_id")
        if not EXACT_COMMIT_RE.fullmatch(commit):
            raise MCPDomainError(
                "invalid_request",
                "commit must be an exact lowercase 40-character Git SHA.",
            )
        return await self._post(
            f"/api/control/v1/services/{quote(service_id, safe='')}/takeovers/",
            {"commit": commit},
        )

    async def get_service_takeover(self, takeover_id: str) -> dict:
        _validate_uuid(takeover_id, "takeover_id")
        return await self._get(
            f"/api/control/v1/takeovers/{quote(takeover_id, safe='')}/"
        )

    async def activate_service_takeover(self, takeover_id: str) -> dict:
        _validate_uuid(takeover_id, "takeover_id")
        return await self._post(
            f"/api/control/v1/takeovers/{quote(takeover_id, safe='')}/activate/",
            {},
        )

    async def cancel_service_takeover(self, takeover_id: str) -> dict:
        _validate_uuid(takeover_id, "takeover_id")
        return await self._post(
            f"/api/control/v1/takeovers/{quote(takeover_id, safe='')}/cancel/",
            {},
        )

    async def create_domain(
        self,
        project_id: str,
        service_id: str,
        hostname: str,
        configure_nginx: bool = True,
        ssl_enabled: bool = False,
    ) -> dict:
        _validate_uuid(project_id, "project_id")
        _validate_uuid(service_id, "service_id")
        if not re.fullmatch(
            r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,63}",
            hostname,
        ):
            raise MCPDomainError("invalid_request", "hostname is invalid.")
        return await self._post(
            f"/api/control/v1/projects/{quote(project_id, safe='')}/domains/",
            {
                "service_id": service_id,
                "hostname": hostname,
                "configure_nginx": configure_nginx,
                "ssl_enabled": ssl_enabled,
            },
        )

    async def enable_domain_ssl(self, domain_id: str) -> dict:
        _validate_uuid(domain_id, "domain_id")
        return await self._post(
            f"/api/control/v1/domains/{quote(domain_id, safe='')}/ssl/",
            {},
        )

    async def deploy_service(self, service_id: str, commit: str | None) -> dict:
        if commit and not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise MCPDomainError("invalid_request", "commit must be an exact lowercase SHA-1.")
        return await self._post(
            f"/api/control/v1/services/{quote(service_id, safe='')}/deployments/",
            {"commit": commit} if commit else {},
        )

    async def get_deployment(self, deployment_id: str) -> dict:
        return await self._get(f"/api/control/v1/deployments/{quote(deployment_id, safe='')}/")

    async def redeploy(self, deployment_id: str) -> dict:
        return await self._post(f"/api/control/v1/deployments/{quote(deployment_id, safe='')}/redeploy/", {})

    async def rollback(self, deployment_id: str) -> dict:
        return await self._post(f"/api/control/v1/deployments/{quote(deployment_id, safe='')}/rollback/", {})

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()
