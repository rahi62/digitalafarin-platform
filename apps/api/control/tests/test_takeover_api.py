from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import (
    Operation,
    Project,
    Server,
    Service,
    ServiceCredential,
    ServicePrincipal,
    ServiceSnapshot,
    ServiceTakeover,
)
from control.security import issue_secret


class TakeoverApiTests(TestCase):
    def setUp(self):
        self.server = Server.objects.create(
            name="Target",
            last_seen_at=timezone.now(),
            disk_percent=25,
        )
        self.project = Project.objects.create(
            name="DigitalAfarin Platform",
            slug="digitalafarin-platform",
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
        principal = ServicePrincipal.objects.create(
            name="web",
            scopes=["operations:create", "operations:read"],
        )
        issued = issue_secret("service")
        ServiceCredential.objects.create(
            principal=principal,
            token_prefix=issued.prefix,
            token_hash=issued.digest,
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")

    def prepare(self, commit="a" * 40):
        return self.client.post(
            f"/api/control/v1/services/{self.service.public_id}/takeovers/",
            {"commit": commit},
            format="json",
        )

    def test_configured_node_service_queues_typed_prepare_only(self):
        response = self.prepare()
        self.assertEqual(response.status_code, 201)
        takeover = ServiceTakeover.objects.get(public_id=response.json()["id"])
        self.assertEqual(takeover.state, ServiceTakeover.STATE_QUEUED)
        self.assertEqual(takeover.requested_commit, "a" * 40)
        operation = takeover.prepare_operation
        self.assertEqual(operation.kind, Operation.KIND_TAKEOVER_PREPARE)
        self.assertEqual(operation.payload, {"takeover_id": str(takeover.public_id)})
        self.assertEqual(Operation.objects.count(), 1)

    def test_prepare_rejects_non_exact_commit(self):
        response = self.prepare("main")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ServiceTakeover.objects.count(), 0)
        self.assertEqual(Operation.objects.count(), 0)

    def test_prepare_rejects_adopted_managed_missing_inventory_and_unsupported_runtime(self):
        cases = [
            ("lifecycle_state", Service.LIFECYCLE_ADOPTED, "service_not_configured"),
            ("lifecycle_state", Service.LIFECYCLE_MANAGED, "service_not_configured"),
            ("runtime", Service.RUNTIME_DJANGO, "unsupported_takeover_runtime"),
        ]
        for field, value, code in cases:
            original = getattr(self.service, field)
            setattr(self.service, field, value)
            self.service.save(update_fields=[field])
            response = self.prepare()
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["error"], code)
            setattr(self.service, field, original)
            self.service.save(update_fields=[field])

        ServiceSnapshot.objects.filter(
            server=self.server, unit_name=self.service.unit_name
        ).delete()
        missing = self.prepare()
        self.assertEqual(missing.status_code, 409)
        self.assertEqual(missing.json()["error"], "inventory_unit_missing")

    def test_prepare_rejects_offline_and_full_disk_server(self):
        self.server.last_seen_at = timezone.now() - timedelta(minutes=5)
        self.server.save(update_fields=["last_seen_at"])
        offline = self.prepare()
        self.assertEqual(offline.status_code, 409)
        self.assertEqual(offline.json()["error"], "server_offline")

        self.server.last_seen_at = timezone.now()
        self.server.disk_percent = 90
        self.server.save(update_fields=["last_seen_at", "disk_percent"])
        full = self.prepare()
        self.assertEqual(full.status_code, 409)
        self.assertEqual(full.json()["error"], "disk_usage_blocked")

    def test_prepare_rejects_incomplete_configured_metadata(self):
        self.service.branch = None
        self.service.save(update_fields=["branch"])
        response = self.prepare()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "service_configuration_incomplete")

    def test_second_active_takeover_is_rejected(self):
        self.assertEqual(self.prepare().status_code, 201)
        second = self.prepare("b" * 40)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"], "takeover_already_active")

    def test_takeover_history_is_secret_free(self):
        created = self.prepare()
        history = self.client.get(
            f"/api/control/v1/services/{self.service.public_id}/takeovers/"
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["items"][0]["id"], created.json()["id"])
        self.assertNotIn("environment", str(history.json()).lower())

    def _mark_prepared(self):
        takeover = ServiceTakeover.objects.get(public_id=self.prepare().json()["id"])
        takeover.state = ServiceTakeover.STATE_PREPARED
        takeover.resolved_commit = takeover.requested_commit
        takeover.source_snapshot = {"user": "deploy"}
        takeover.source_fingerprint = "f" * 64
        takeover.release_name = "20260920-120000-aaaaaaa"
        takeover.release_path = (
            "/srv/digitalafarin/apps/digitalafarin-platform/"
            "platform-web/releases/20260920-120000-aaaaaaa"
        )
        takeover.save()
        return takeover

    def test_prepared_takeover_queues_activate_operation_only_once(self):
        takeover = self._mark_prepared()
        response = self.client.post(
            f"/api/control/v1/takeovers/{takeover.public_id}/activate/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        takeover.refresh_from_db()
        self.assertEqual(takeover.activate_operation.kind, Operation.KIND_TAKEOVER_ACTIVATE)
        self.assertEqual(
            takeover.activate_operation.payload,
            {"takeover_id": str(takeover.public_id)},
        )
        duplicate = self.client.post(
            f"/api/control/v1/takeovers/{takeover.public_id}/activate/",
            {},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_prepared_takeover_can_be_canceled_without_operation(self):
        takeover = self._mark_prepared()
        before = Operation.objects.count()
        response = self.client.post(
            f"/api/control/v1/takeovers/{takeover.public_id}/cancel/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        takeover.refresh_from_db()
        self.assertEqual(takeover.state, ServiceTakeover.STATE_CANCELED)
        self.assertEqual(Operation.objects.count(), before)

    def test_takeover_detail_is_readable(self):
        takeover = self._mark_prepared()
        response = self.client.get(f"/api/control/v1/takeovers/{takeover.public_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "prepared")

    def test_activation_rejects_prepared_takeover_if_service_is_no_longer_configured(self):
        takeover = self._mark_prepared()
        self.service.lifecycle_state = Service.LIFECYCLE_MANAGED
        self.service.save(update_fields=["lifecycle_state"])

        response = self.client.post(
            f"/api/control/v1/takeovers/{takeover.public_id}/activate/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "service_not_configured")
        takeover.refresh_from_db()
        self.assertIsNone(takeover.activate_operation_id)
