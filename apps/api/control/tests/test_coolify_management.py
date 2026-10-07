import io
import json
import uuid
from unittest.mock import MagicMock, call, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from control.coolify_client import CoolifyConfigurationError, CoolifyUpstreamError
from control.models import AuditEvent, CoolifyManagedApplication, ServiceCredential, ServicePrincipal
from control.security import issue_secret

REPOSITORY = "https://github.com/example/application.git"
POLICY = {"migration": {
    "principals": ["manager"], "project_uuid": "project-1", "environment_uuid": "env-1",
    "server_uuid": "server-1", "destination_uuid": "destination-1",
    "repositories": [REPOSITORY], "domains": ["https://app.example.com"],
    "environment_keys": ["DATABASE_URL", "NIXPACKS_BUILD_CMD"],
}}
BASE = "/api/control/v1/coolify/"


@override_settings(COOLIFY_MANAGEMENT_TARGETS=POLICY)
class CoolifyManagementTests(TestCase):
    def setUp(self):
        self.principal = ServicePrincipal.objects.create(name="manager", scopes=["coolify:read", "coolify:manage", "coolify:deploy", "coolify:delete"])
        secret = issue_secret("service")
        self.credential = ServiceCredential.objects.create(principal=self.principal, token_prefix=secret.prefix, token_hash=secret.digest)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {secret.cleartext}")
        self.upstream = MagicMock()
        self.upstream.create_application.return_value = {"uuid": "app-1", "token": "UPSTREAM-SECRET"}
        self.upstream.get_application.return_value = {"uuid": "app-1", "name": "demo", "git_repository": REPOSITORY, "password": "UPSTREAM-SECRET"}
        self.upstream.get_environment.return_value = {"applications": [{"uuid": "app-1"}]}
        self.upstream.list_server_resources.return_value = [{"uuid": "app-1"}]
        self.upstream.deploy_application.return_value = {"deployment_uuid": "deployment-1", "message": "UPSTREAM-SECRET"}
        self.upstream.start_application.return_value = {"deployment_uuid": "deployment-1"}
        self.upstream.restart_application.return_value = {"deployment_uuid": "deployment-1"}
        self.upstream.stop_application.return_value = {"message": "UPSTREAM-SECRET"}
        self.upstream.get_deployment.return_value = {"deployment_uuid": "deployment-1", "application_id": 42, "status": "finished", "logs": json.dumps([{"output": "UPSTREAM-SECRET"}] * 250), "configuration_snapshot": {"password": "UPSTREAM-SECRET"}}
        self.upstream.list_application_deployments.return_value = {"deployments": [{"deployment_uuid": "deployment-1", "application_id": 42, "status": "finished"}]}
        self.mock = patch("control.coolify_management_views.CoolifyClient", return_value=self.upstream)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def register(self):
        return CoolifyManagedApplication.objects.create(request_id=uuid.uuid4(), application_uuid="app-1", target="migration", principal=self.principal)

    def payload(self, **overrides):
        return {"request_id": str(uuid.uuid4()), "target": "migration", "name": "demo", "git_repository": REPOSITORY, "git_branch": "main", "build_pack": "dockerfile", "ports_exposes": [3000], **overrides}

    def post(self, suffix, data=None):
        return self.client.post(BASE + suffix, data if data is not None else {}, format="json")

    def test_create_selects_reviewed_placement_without_deploying_and_reserves_request(self):
        data = self.payload(base_directory="/apps/web", limits_cpus="1.50", domains=["https://app.example.com"])
        response = self.post("applications/", data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"application_uuid": "app-1"})
        sent = self.upstream.create_application.call_args.args[0]
        self.assertEqual(sent["ports_exposes"], "3000")
        self.assertEqual(sent["environment_uuid"], "env-1")
        self.assertEqual(sent["destination_uuid"], "destination-1")
        self.assertFalse(sent["instant_deploy"])
        self.assertFalse(sent["is_auto_deploy_enabled"])
        self.assertFalse(sent["autogenerate_domain"])
        self.assertEqual(self.post("applications/", data).status_code, 400)
        self.upstream.create_application.assert_called_once()
        self.assertNotIn("UPSTREAM-SECRET", str(list(AuditEvent.objects.values())))

    def test_uncertain_create_is_not_automatically_retried(self):
        self.upstream.create_application.side_effect = CoolifyUpstreamError("SECRET")
        data = self.payload()
        response = self.post("applications/", data)
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("SECRET", response.content.decode())
        self.assertEqual(self.post("applications/", data).status_code, 400)
        self.upstream.create_application.assert_called_once()

    def test_unapproved_repository_target_domain_are_denied(self):
        for change in [{"git_repository": "https://evil.example/app.git"}, {"target": "unknown"}, {"domains": ["https://production.example.com"]}]:
            with self.subTest(change=change):
                self.assertEqual(self.post("applications/", self.payload(**change)).status_code, 403)
        self.upstream.create_application.assert_not_called()

    def test_unknown_and_dangerous_fields_paths_ports_and_urls_are_rejected(self):
        for change in [
            {"start_command": "id"}, {"dockerfile": "FROM scratch"}, {"docker_compose_raw": "secret"},
            {"build_pack": "dockercompose"}, {"base_directory": "/../etc"}, {"base_directory": "/x;id"},
            {"git_repository": "https://user:secret@github.com/example/application.git"},
            {"git_branch": "main;id"}, {"ports_exposes": [0]}, {"ports_exposes": [65536]},
            {"ports_mappings": "22:22"}, {"name": "digitalafarin-platform-api"}, {"name": "my-mcp"},
            {"domains": ["https://user:secret@example.com"]}, {"domains": ["https://example.com/path"]},
        ]:
            with self.subTest(change=change):
                self.assertEqual(self.post("applications/", self.payload(**change)).status_code, 400)
        self.assertEqual(self.post("applications/", ["invalid"]).status_code, 400)
        self.upstream.create_application.assert_not_called()

    def test_read_scope_cannot_mutate_or_delete(self):
        self.register()
        self.principal.scopes = ["coolify:read"]
        self.principal.save()
        for path, payload in [("applications/", self.payload()), ("applications/app-1/configure/", {"ports_exposes": [80]}), ("applications/app-1/deploy/", {}), ("applications/app-1/delete/", {"confirm_application_uuid": "app-1"}), ("applications/app-1/environment/create/", {"key": "DATABASE_URL", "value": "secret"})]:
            with self.subTest(path=path):
                self.assertEqual(self.post(path, payload).status_code, 403)
        self.upstream.get_application.assert_not_called()

    def test_manage_and_deploy_scopes_do_not_authorize_deletion(self):
        self.register()
        self.principal.scopes = ["coolify:manage", "coolify:deploy"]
        self.principal.save()
        self.assertEqual(self.post("applications/app-1/delete/", {"confirm_application_uuid": "app-1"}).status_code, 403)
        self.upstream.delete_application.assert_not_called()

    def test_authentication_revocation_and_disabled_principal(self):
        self.client.credentials()
        self.assertIn(self.post("applications/", self.payload()).status_code, {401, 403})
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid")
        self.assertIn(self.post("applications/", self.payload()).status_code, {401, 403})
        self.upstream.create_application.assert_not_called()

    def test_unmanaged_cross_principal_and_revoked_policy_are_denied(self):
        self.assertEqual(self.post("applications/app-1/deploy/").status_code, 403)
        row = self.register()
        other = ServicePrincipal.objects.create(name="other", scopes=["coolify:manage"])
        row.principal = other
        row.save()
        self.assertEqual(self.post("applications/app-1/deploy/").status_code, 403)
        row.principal = self.principal
        row.save()
        with override_settings(COOLIFY_MANAGEMENT_TARGETS={}):
            self.assertEqual(self.post("applications/app-1/deploy/").status_code, 403)
        self.upstream.deploy_application.assert_not_called()

    def test_protected_name_and_repository_drift_block_management(self):
        self.register()
        self.upstream.get_application.return_value["name"] = "digitalafarin-platform-api"
        self.assertEqual(self.post("applications/app-1/stop/").status_code, 403)
        self.upstream.get_application.return_value["name"] = "demo"
        self.upstream.get_application.return_value["git_repository"] = "https://evil.example/repo"
        self.assertEqual(self.post("applications/app-1/stop/").status_code, 403)
        self.upstream.stop_application.assert_not_called()

    def test_configure_does_not_echo_upstream_configuration(self):
        self.register()
        response = self.post("applications/app-1/configure/", {"ports_exposes": [3000, 3001], "limits_memory": "512M"})
        self.assertEqual(response.status_code, 200)
        self.upstream.update_application.assert_called_once_with("app-1", {"ports_exposes": "3000,3001", "limits_memory": "512M"})
        self.assertEqual(self.post("applications/app-1/configure/").status_code, 400)

    def test_environment_write_is_literal_write_only_and_not_audited(self):
        self.register()
        for action in ["create", "update"]:
            response = self.post(f"applications/app-1/environment/{action}/", {"key": "DATABASE_URL", "value": "PASSWORD-SECRET\nsecond-line", "is_buildtime": True})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("PASSWORD-SECRET", response.content.decode())
            sent = getattr(self.upstream, f"{action}_environment_variable").call_args.args[1]
            self.assertTrue(sent["is_literal"])
            self.assertTrue(sent["is_shown_once"])
            self.assertTrue(sent["is_multiline"])
            self.assertTrue(sent["is_buildtime"])
        self.assertNotIn("PASSWORD-SECRET", str(list(AuditEvent.objects.values())))
        for value, expected in [({"key": "UNAPPROVED", "value": "secret"}, 403), ({"key": "NIXPACKS_BUILD_CMD", "value": "id"}, 400), ({"key": "DATABASE_URL", "value": "x", "is_runtime": False}, 400), ({"key": "DATABASE_URL", "value": "x" * 16385}, 400)]:
            self.assertEqual(self.post("applications/app-1/environment/create/", value).status_code, expected)

    def test_environment_read_projects_metadata_only(self):
        self.register()
        self.upstream.list_environment_variables.return_value = [{"key": "DATABASE_URL", "value": "SECRET", "comment": "SECRET", "is_runtime": True, "nested": {"value": "SECRET"}}, {"key": "SECRET", "value": "SECRET"}]
        response = self.client.get(BASE + "applications/app-1/environment/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [{"key": "DATABASE_URL", "is_buildtime": False, "is_runtime": True}]})

    def test_deploy_redeploy_start_stop_restart_mapping(self):
        self.register()
        for action in ["deploy", "redeploy", "start", "stop", "restart"]:
            response = self.post(f"applications/app-1/{action}/")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("UPSTREAM-SECRET", response.content.decode())
        self.upstream.deploy_application.assert_any_call("app-1")
        self.upstream.deploy_application.assert_any_call("app-1", force=True)
        for action in ["start", "stop", "restart"]:
            getattr(self.upstream, f"{action}_application").assert_called_once_with("app-1")
        self.assertEqual(self.post("applications/app-1/deploy/", {"command": "id"}).status_code, 400)

    def test_deployment_status_logs_bounds_and_cross_application_access(self):
        self.register()
        path = BASE + "applications/app-1/deployments/deployment-1/"
        response = self.client.get(path)
        self.assertEqual(response.json(), {"deployment_uuid": "deployment-1", "status": "finished"})
        response = self.client.get(path + "logs/?lines=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 2)
        self.assertTrue(response.json()["truncated"])
        self.assertNotIn("UPSTREAM-SECRET", response.content.decode())
        for query in ["lines=0", "lines=201", "lines=hello", "command=id"]:
            self.assertEqual(self.client.get(path + "logs/?" + query).status_code, 400)
        self.upstream.get_deployment.return_value["application_id"] = 100
        self.assertEqual(self.client.get(path).status_code, 403)

    def test_deployment_list_and_sensitive_logs_unavailable(self):
        self.register()
        self.upstream.list_application_deployments.return_value = {"deployments": [self.upstream.get_deployment.return_value] * 30}
        response = self.client.get(BASE + "applications/app-1/deployments/")
        self.assertEqual(len(response.json()["items"]), 20)
        self.assertNotIn("UPSTREAM-SECRET", response.content.decode())
        del self.upstream.get_deployment.return_value["logs"]
        response = self.client.get(BASE + "applications/app-1/deployments/deployment-1/logs/")
        self.assertFalse(response.json()["available"])

    def test_delete_requires_exact_confirmation_and_disables_later_access(self):
        self.register()
        self.assertEqual(self.post("applications/app-1/delete/").status_code, 400)
        self.assertEqual(self.post("applications/app-1/delete/", {"confirm_application_uuid": "other"}).status_code, 400)
        self.upstream.delete_application.assert_not_called()
        response = self.post("applications/app-1/delete/", {"confirm_application_uuid": "app-1"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["volumes_preserved"])
        self.assertEqual(self.post("applications/app-1/start/").status_code, 403)

    def test_configuration_failures_are_safe_and_audited(self):
        with patch("control.coolify_management_views.CoolifyClient", side_effect=CoolifyConfigurationError("SECRET")):
            response = self.post("applications/", self.payload())
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("SECRET", response.content.decode())
        self.assertEqual(AuditEvent.objects.filter(event_type="mcp.coolify.completed").last().metadata["http_status"], 503)

    def test_target_and_environment_discovery(self):
        response = self.client.get(BASE + "targets/")
        self.assertEqual(response.json()["items"][0]["environment_uuid"], "env-1")
        self.assertNotIn("principals", response.json()["items"][0])
        self.upstream.list_environments.return_value = [{"uuid": "env-1", "secret": "SECRET"}]
        response = self.client.get(BASE + "projects/project-1/environments/")
        self.assertEqual(response.json(), {"items": [{"uuid": "env-1"}]})

    def test_explicit_scope_grant_preserves_credential(self):
        self.principal.scopes = ["coolify:read"]
        self.principal.save()
        output = io.StringIO()
        call_command("grant_coolify_scope", "manager", scope="coolify:delete", stdout=output)
        self.principal.refresh_from_db()
        self.assertEqual(self.principal.scopes, ["coolify:read", "coolify:delete"])
        self.assertEqual(ServiceCredential.objects.count(), 1)
        self.assertNotIn("da_service_", output.getvalue())

    def test_logs_allow_only_exact_constant_lifecycle_messages(self):
        self.register()
        self.upstream.get_deployment.return_value["logs"] = json.dumps([
            {"output": "Building docker image completed."},
            {"output": "Building docker image completed. SECRET"},
            {"output": {"secret": "SECRET"}},
            {"output": "postgresql://user:password@example.com/db"},
            {"output": "-----BEGIN PRIVATE KEY-----secret"},
        ])
        response = self.client.get(BASE + "applications/app-1/deployments/deployment-1/logs/")
        self.assertEqual(response.json()["items"][0]["output"], "Building docker image completed.")
        self.assertTrue(all(item["output"] == "[REDACTED]" for item in response.json()["items"][1:]))

    def test_revoked_credentials_and_inactive_principal_reject_management(self):
        from django.utils import timezone
        self.principal.is_active = False
        self.principal.save()
        self.assertEqual(self.post("applications/", self.payload()).status_code, 401)
        self.principal.is_active = True
        self.principal.save()
        self.credential.revoked_at = timezone.now()
        self.credential.save()
        self.assertEqual(self.post("applications/", self.payload()).status_code, 401)
        self.upstream.create_application.assert_not_called()

    def test_malformed_upstream_and_domain_port_are_safe(self):
        self.register()
        self.assertEqual(self.post("applications/app-1/configure/", {"domains": ["https://example.com:99999"]}).status_code, 400)
        self.upstream.get_deployment.return_value["status"] = {"secret": "SECRET"}
        response = self.client.get(BASE + "applications/app-1/deployments/deployment-1/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unknown")
        self.upstream.get_deployment.return_value = ["SECRET"]
        response = self.client.get(BASE + "applications/app-1/deployments/deployment-1/")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("SECRET", response.content.decode())

    def test_private_repository_uses_server_configured_github_app_only(self):
        policy = {"migration": {**POLICY["migration"], "github_app_uuid": "github-app-1"}}
        self.upstream.create_github_application.return_value = {"uuid": "app-1"}
        with override_settings(COOLIFY_MANAGEMENT_TARGETS=policy):
            response = self.post("applications/", self.payload())
        self.assertEqual(response.status_code, 200)
        self.upstream.create_application.assert_not_called()
        self.assertEqual(self.upstream.create_github_application.call_args.args[0]["github_app_uuid"], "github-app-1")
        self.assertEqual(self.post("applications/", self.payload(github_app_uuid="caller-supplied")).status_code, 400)

    def test_github_repository_normalization_and_placement_drift(self):
        self.register()
        self.upstream.get_application.return_value["git_repository"] = "example/application.git"
        self.assertEqual(self.post("applications/app-1/deploy/").status_code, 200)
        self.upstream.get_application.return_value["git_repository"] = "example/application"
        self.assertEqual(self.post("applications/app-1/deploy/").status_code, 200)
        self.upstream.get_environment.return_value = {"applications": []}
        self.assertEqual(self.post("applications/app-1/deploy/").status_code, 403)
        self.upstream.get_environment.return_value = {"applications": [{"uuid": "app-1"}]}
        self.upstream.list_server_resources.return_value = []
        self.assertEqual(self.post("applications/app-1/deploy/").status_code, 403)

    def application_routes(self):
        return [
            ("post", "applications/app-1/configure/", {"ports_exposes": [3000]}, "coolify:manage"),
            ("post", "applications/app-1/environment/create/", {"key": "DATABASE_URL", "value": "SECRET"}, "coolify:manage"),
            ("post", "applications/app-1/environment/update/", {"key": "DATABASE_URL", "value": "SECRET"}, "coolify:manage"),
            *[("post", f"applications/app-1/{action}/", {}, "coolify:deploy")
              for action in ["deploy", "redeploy", "start", "stop", "restart"]],
            ("post", "applications/app-1/delete/", {"confirm_application_uuid": "app-1"}, "coolify:delete"),
            ("get", "applications/app-1/environment/", {}, "coolify:read"),
            ("get", "applications/app-1/deployments/", {}, "coolify:read"),
            ("get", "applications/app-1/deployments/deployment-1/", {}, "coolify:read"),
            ("get", "applications/app-1/deployments/deployment-1/logs/", {}, "coolify:read"),
        ]

    def test_every_management_route_requires_its_explicit_scope(self):
        self.register()
        routes = self.application_routes() + [
            ("post", "applications/", self.payload(), "coolify:manage"),
            ("get", "targets/", {}, "coolify:read"),
            ("get", "projects/project-1/environments/", {}, "coolify:read"),
        ]
        scopes = {"coolify:read", "coolify:manage", "coolify:deploy", "coolify:delete"}
        for method, path, data, required in routes:
            with self.subTest(path=path, missing=required):
                self.principal.scopes = sorted(scopes - {required})
                self.principal.save()
                self.upstream.reset_mock()
                response = getattr(self.client, method)(BASE + path, data, format="json")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.upstream.mock_calls, [])
                self.assertNotIn("SECRET", response.content.decode())

    def test_every_application_route_denies_cross_principal_and_deleted_ownership(self):
        row = self.register()
        other = ServicePrincipal.objects.create(name="other", scopes=[])
        for owner, deleted in [(other, False), (self.principal, True)]:
            row.principal, row.deleted = owner, deleted
            row.save()
            for method, path, data, _ in self.application_routes():
                with self.subTest(path=path, deleted=deleted):
                    self.upstream.reset_mock()
                    response = getattr(self.client, method)(BASE + path, data, format="json")
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(self.upstream.mock_calls, [call.close()])
