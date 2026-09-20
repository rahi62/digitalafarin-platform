from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import (
    AgentCredential,
    Operation,
    Project,
    Server,
    Service,
    ServiceSnapshot,
    ServiceTakeover,
)
from control.security import issue_secret
from control.services.takeovers import queue_takeover_prepare


class TakeoverResultTests(TestCase):
    def setUp(self):
        self.server = Server.objects.create(
            name="Target", last_seen_at=timezone.now(), disk_percent=25
        )
        self.project = Project.objects.create(
            name="DigitalAfarin Platform", slug="digitalafarin-platform"
        )
        self.service = Service.objects.create(
            project=self.project,
            name="platform-web",
            executor=Service.EXECUTOR_SYSTEMD,
            unit_name="digitalafarin-platform-web.service",
            lifecycle_state=Service.LIFECYCLE_CONFIGURED,
            repository="https://github.com/example/platform.git",
            branch="main",
            root_directory="apps/web",
            runtime=Service.RUNTIME_NODE,
            install_configuration={"package_manager": "npm", "lockfile": "package-lock.json"},
            build_configuration={"build_script": "build"},
            service_port=9751,
            target_server=self.server,
        )
        ServiceSnapshot.objects.create(
            server=self.server,
            unit_name=self.service.unit_name,
            description="Platform Web",
            load_state="loaded",
            active_state="active",
            sub_state="running",
        )
        agent_secret = issue_secret("agent")
        AgentCredential.objects.create(
            server=self.server,
            token_prefix=agent_secret.prefix,
            token_hash=agent_secret.digest,
        )
        self.agent = APIClient()
        self.agent.credentials(
            HTTP_AUTHORIZATION=f"Bearer {agent_secret.cleartext}"
        )
        self.takeover, self.operation = queue_takeover_prepare(
            service=self.service,
            exact_commit="a" * 40,
            requested_by="web",
        )

    def claim(self):
        response = self.agent.post("/api/agent/v1/operations/claim", {}, format="json")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def prepared_result(self):
        return {
            "takeover_id": str(self.takeover.public_id),
            "final_state": "prepared",
            "resolved_commit": "a" * 40,
            "source_snapshot": {
                "unit_name": self.service.unit_name,
                "fragment_path": "/etc/systemd/system/digitalafarin-platform-web.service",
                "drop_in_paths": [],
                "user": "deploy",
                "group": "www-data",
                "working_directory": "/opt/digitalafarin-platform/apps/web",
                "exec_start_path": "/usr/bin/npm",
                "exec_start_argv": [
                    "/usr/bin/npm", "start", "--", "--hostname", "127.0.0.1", "--port", "9751"
                ],
                "environment_file_paths": ["/etc/digitalafarin-platform/web.env"],
                "restart_policy": "on-failure",
                "restart_delay_usec": 3_000_000,
                "source_file_hashes": [
                    {
                        "path": "/etc/systemd/system/digitalafarin-platform-web.service",
                        "sha256": "1" * 64,
                    }
                ],
            },
            "source_fingerprint": "2" * 64,
            "release_name": "20260920-120000-aaaaaaa",
            "release_path": (
                "/srv/digitalafarin/apps/digitalafarin-platform/"
                "platform-web/releases/20260920-120000-aaaaaaa"
            ),
            "events": [
                {"state": "inspecting", "message": ""},
                {"state": "preparing", "message": ""},
                {"state": "prepared", "message": ""},
            ],
        }

    def test_prepare_claim_context_is_server_derived_and_secret_free(self):
        claim = self.claim()
        execution = claim["operation"]["execution"]
        self.assertEqual(execution["takeover_id"], str(self.takeover.public_id))
        self.assertEqual(execution["unit_name"], self.service.unit_name)
        self.assertEqual(execution["repository"], self.service.repository)
        self.assertEqual(execution["exact_commit"], "a" * 40)
        self.assertEqual(execution["root_directory"], "apps/web")
        self.assertEqual(execution["runtime"], "node-nextjs")
        self.assertNotIn("environment", execution)
        self.assertEqual(
            Operation.objects.get(pk=self.operation.pk).payload,
            {"takeover_id": str(self.takeover.public_id)},
        )

    def test_prepare_start_and_completion_persist_prepared_snapshot(self):
        claim = self.claim()
        operation_id = claim["operation"]["id"]
        token = claim["claim_token"]
        started = self.agent.post(
            f"/api/agent/v1/operations/{operation_id}/started",
            {"claim_token": token},
            format="json",
        )
        self.assertEqual(started.status_code, 200)
        self.takeover.refresh_from_db()
        self.assertEqual(self.takeover.state, ServiceTakeover.STATE_INSPECTING)

        completed = self.agent.post(
            f"/api/agent/v1/operations/{operation_id}/complete",
            {
                "claim_token": token,
                "succeeded": True,
                "result": self.prepared_result(),
            },
            format="json",
        )
        self.assertEqual(completed.status_code, 200)
        self.takeover.refresh_from_db()
        self.service.refresh_from_db()
        self.assertEqual(self.takeover.state, ServiceTakeover.STATE_PREPARED)
        self.assertEqual(self.takeover.source_snapshot["user"], "deploy")
        self.assertEqual(self.takeover.source_fingerprint, "2" * 64)
        self.assertEqual(self.takeover.release_name, "20260920-120000-aaaaaaa")
        self.assertEqual(self.service.lifecycle_state, Service.LIFECYCLE_CONFIGURED)

    def test_reapplying_same_prepare_result_is_idempotent(self):
        from control.services.takeovers import apply_takeover_result

        apply_takeover_result(
            self.operation,
            succeeded=True,
            result=self.prepared_result(),
            error_code="",
            error_message="",
        )
        apply_takeover_result(
            self.operation,
            succeeded=True,
            result=self.prepared_result(),
            error_code="",
            error_message="",
        )
        self.takeover.refresh_from_db()
        self.assertEqual(self.takeover.state, ServiceTakeover.STATE_PREPARED)

    def _prepare_for_activation(self):
        from control.services.takeovers import apply_takeover_result, queue_takeover_activation

        apply_takeover_result(
            self.operation,
            succeeded=True,
            result=self.prepared_result(),
            error_code="",
            error_message="",
        )
        self.takeover.refresh_from_db()
        operation = queue_takeover_activation(
            takeover=self.takeover,
            requested_by="web",
        )
        return operation

    def activation_result(self, final_state="succeeded"):
        return {
            "takeover_id": str(self.takeover.public_id),
            "final_state": final_state,
            "resolved_commit": "a" * 40,
            "release_name": "20260920-120000-aaaaaaa",
            "previous_current_path": None,
            "managed_dropin_path": (
                "/etc/systemd/system/digitalafarin-platform-web.service.d/"
                "90-digitalafarin-managed.conf"
            ),
            "events": [
                {"state": "activating", "message": ""},
                {"state": "verifying", "message": ""},
                {"state": final_state, "message": ""},
            ],
        }

    def test_successful_activation_marks_managed_and_creates_one_takeover_release(self):
        from control.models import Release
        from control.services.takeovers import apply_takeover_result, mark_takeover_operation_started

        operation = self._prepare_for_activation()
        mark_takeover_operation_started(operation)
        result = self.activation_result("succeeded")
        apply_takeover_result(
            operation,
            succeeded=True,
            result=result,
            error_code="",
            error_message="",
        )
        # Completion retries are idempotent.
        apply_takeover_result(
            operation,
            succeeded=True,
            result=result,
            error_code="",
            error_message="",
        )
        self.takeover.refresh_from_db()
        self.service.refresh_from_db()
        self.assertEqual(self.takeover.state, ServiceTakeover.STATE_SUCCEEDED)
        self.assertEqual(self.service.lifecycle_state, Service.LIFECYCLE_MANAGED)
        release = Release.objects.get(takeover=self.takeover)
        self.assertIsNone(release.deployment_id)
        self.assertIsNotNone(release.activated_at)
        self.assertEqual(Release.objects.filter(takeover=self.takeover).count(), 1)

    def test_rolled_back_activation_leaves_service_configured_without_release(self):
        from control.models import Release
        from control.services.takeovers import apply_takeover_result, mark_takeover_operation_started

        operation = self._prepare_for_activation()
        mark_takeover_operation_started(operation)
        apply_takeover_result(
            operation,
            succeeded=True,
            result=self.activation_result("rolled_back"),
            error_code="",
            error_message="",
        )
        self.takeover.refresh_from_db()
        self.service.refresh_from_db()
        self.assertEqual(self.takeover.state, ServiceTakeover.STATE_ROLLED_BACK)
        self.assertEqual(self.service.lifecycle_state, Service.LIFECYCLE_CONFIGURED)
        self.assertFalse(Release.objects.filter(takeover=self.takeover).exists())

    def test_rollback_failed_never_marks_managed(self):
        from control.models import Release
        from control.services.takeovers import apply_takeover_result, mark_takeover_operation_started

        operation = self._prepare_for_activation()
        mark_takeover_operation_started(operation)
        apply_takeover_result(
            operation,
            succeeded=False,
            result={},
            error_code="takeover_rollback_failed",
            error_message="rollback health failed",
        )
        self.takeover.refresh_from_db()
        self.service.refresh_from_db()
        self.assertEqual(self.takeover.state, ServiceTakeover.STATE_ROLLBACK_FAILED)
        self.assertEqual(self.service.lifecycle_state, Service.LIFECYCLE_CONFIGURED)
        self.assertFalse(Release.objects.filter(takeover=self.takeover).exists())

    def test_activation_result_rejects_previous_current_path_with_parent_escape(self):
        from control.services.takeovers import (
            TakeoverError,
            apply_takeover_result,
            mark_takeover_operation_started,
        )

        operation = self._prepare_for_activation()
        mark_takeover_operation_started(operation)
        result = self.activation_result("succeeded")
        result["previous_current_path"] = (
            "/srv/digitalafarin/apps/digitalafarin-platform/"
            "platform-web/releases/../outside"
        )
        with self.assertRaises(TakeoverError):
            apply_takeover_result(
                operation,
                succeeded=True,
                result=result,
                error_code="",
                error_message="",
            )
