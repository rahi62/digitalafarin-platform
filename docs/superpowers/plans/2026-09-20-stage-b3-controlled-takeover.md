# Stage B3 Controlled Takeover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-phase controlled takeover that moves an existing `configured` `node-nextjs + systemd` service to `managed` only after an exact-commit immutable release is prepared, the original systemd configuration is durably fingerprinted, activation passes two consecutive loopback health checks, and rollback is proven.

**Architecture:** Persist a `ServiceTakeover` workflow in Django and split takeover into PREPARE and ACTIVATE typed Operations. PREPARE is non-mutating: inspect/fingerprint the source unit and build an exact-commit release as the source service user; ACTIVATE rechecks the fingerprint, atomically switches `current`, installs one managed systemd drop-in, restarts only the exact service through a dedicated takeover executor, and either commits `configured -> managed` or restores the original service behavior. The existing protected-service lock remains unchanged for generic service operations.

**Tech Stack:** Django 5.2 + DRF, PostgreSQL/SQLite test DB, Python 3.12 Host Agent, systemd, Git, npm/Next.js 16, Python MCP SDK + httpx, Next.js/TypeScript control UI, pytest, Django TestCase, Node built-in test runner.

**Spec:** `docs/superpowers/specs/2026-09-20-stage-b3-controlled-takeover-design.md`

## Global Constraints

- First concrete takeover runtime is exactly `node-nextjs + systemd`.
- First production candidate is `digitalafarin-platform-web.service`; Oily is excluded from Stage B3 acceptance.
- PREPARE must not change `current`, write a systemd drop-in, call `daemon-reload`, or restart the service.
- ACTIVATE may mutate only the derived `current` symlink and `/etc/systemd/system/<unit>.d/90-digitalafarin-managed.conf`, then reload/restart the exact configured unit.
- The base systemd unit is never rewritten.
- Generic start/stop/restart protection for `digitalafarin-platform-*` remains unchanged.
- The caller never supplies shell text, an arbitrary unit name, a filesystem path, an executable, or environment values to takeover execution.
- Takeover accepts only an exact lowercase 40-character Git SHA.
- Build commands for takeover run as the non-root source systemd `User`; the Agent remains privileged only for filesystem/systemd control.
- Runtime environment file contents and environment values never enter takeover snapshots, Operation payloads, API responses, MCP results, or audit metadata.
- Source fingerprint uses stable effective settings plus hashes of the base unit/drop-ins and excludes PID/start-time/transient runtime fields.
- ACTIVATE must abort before mutation if the current fingerprint differs from the prepared fingerprint.
- `Service.lifecycle_state` remains `configured` on prepare failure, activation failure, successful rollback, and rollback failure.
- `Service.lifecycle_state` changes to `managed` only after successful activation and health verification.
- A successful takeover creates the first managed `Release`; every Release has exactly one provenance source: Deployment XOR ServiceTakeover.
- Health verification for takeover requires two consecutive successful loopback HTTP responses.
- Disk usage `>= 90%` blocks prepare; `>= 80%` is retained as warning metadata.
- Stage B3 must work with the existing outbound typed Operation protocol; it does not add a live progress channel.

## Review Focus

1. **Noisy `systemctl show ExecStart` output:** PID/start timestamps must not alter fingerprints; test the parser against two outputs with different runtime fields and require equal fingerprints.
2. **Administrator changes after PREPARE:** changing a unit/drop-in file before ACTIVATE must return `service_configuration_changed` before `current`, drop-in, or restart mutation.
3. **Unexpected pre-existing `current` symlink:** a link outside the derived service `releases/` directory must block activation rather than being followed or overwritten.
4. **Unsafe service identity:** missing users and `User=root` must block PREPARE before clone/build; no command may run as root on the takeover build path.
5. **Agent completion retries:** applying the same successful PREPARE or ACTIVATE result twice must be idempotent and must not duplicate a Release or regress takeover/service state.

---

## File Map

### Django persistence and domain
- Modify `apps/api/control/models.py` — takeover states/model, two takeover Operation kinds, nullable Release deployment provenance, takeover provenance constraint.
- Create `apps/api/control/migrations/0015_controlled_takeover.py` — generated migration for Stage B3 schema and Operation choice state.
- Create `apps/api/control/takeover_serializers.py` — exact-SHA input and secret-free takeover representation.
- Create `apps/api/control/services/takeovers.py` — admission, state transitions, operation queueing, result validation/finalization, audit.
- Modify `apps/api/control/services/execution.py` — public health-context builder and execution contexts for prepare/activate Operations.
- Create `apps/api/control/takeover_views.py` — prepare/history/detail/activate/cancel views.
- Modify `apps/api/control/control_urls.py` — Stage B3 routes.
- Modify `apps/api/control/agent_views.py` — takeover start/result hooks around the existing Agent Operation lifecycle.
- Create `apps/api/control/tests/test_takeover_models.py` — constraints/provenance/concurrency.
- Create `apps/api/control/tests/test_takeover_api.py` — admission/routes/read/cancel/typed Operation coverage.
- Create `apps/api/control/tests/test_takeover_results.py` — Agent start/completion, idempotency, final managed/rollback outcomes.

### Host Agent
- Modify `agent/digitalafarin_agent/releases.py` — optional injected command runner so takeover Git operations can run as source service user without changing current deployment behavior.
- Create `agent/digitalafarin_agent/takeover_systemd.py` — stable systemd inspection/fingerprint, derived drop-in, safe current/drop-in mutation, dedicated exact-unit restart/reload.
- Create `agent/digitalafarin_agent/takeover.py` — PREPARE and ACTIVATE orchestration, run-as-user command execution, Next artifact validation, rollback.
- Modify `agent/digitalafarin_agent/health.py` — bounded two-consecutive-success health helper.
- Modify `agent/digitalafarin_agent/operations.py` — dispatch only the two typed takeover Operation kinds.
- Modify `agent/tests/test_release_engine.py` — injected command runner coverage.
- Create `agent/tests/test_takeover_systemd.py` — stable fingerprint and systemd mutation safety.
- Create `agent/tests/test_takeover.py` — PREPARE/ACTIVATE/rollback execution behavior.
- Modify `agent/tests/test_operations.py` — typed dispatch and preserved generic protected-unit rejection.

### MCP
- Modify `mcp/digitalafarin_vps_mcp/control_plane.py` — four typed takeover client methods and stable domain-error propagation.
- Modify `mcp/digitalafarin_vps_mcp/server.py` — prepare/get/activate/cancel tools.
- Modify `mcp/tests/test_control_plane.py` — exact request mapping.
- Modify `mcp/tests/test_server.py` — discovery/call coverage.
- Modify `mcp/tests/test_server_contract_static.py` — allowlist the four new tools and keep arbitrary execution absent.

### Web
- Create `apps/web/lib/takeovers.ts` — exact SHA validator, request builders, presentation helpers.
- Create `apps/web/lib/takeovers.test.ts` — pure tests for request shape and takeover-state presentation.
- Modify `apps/web/lib/control-plane.ts` — Takeover types/client methods and two new Operation kind literals.
- Create `apps/web/app/services/takeover-actions.ts` — server actions for prepare/activate/cancel.
- Modify `apps/web/app/services/[serviceId]/page.tsx` — configured-service takeover UI and prepared activation UI.

### Operations documentation
- Modify `docs/migration-runbook.md` — Stage B3 deploy-before-takeover sequence, production PREPARE/ACTIVATE acceptance, rollback verification, and explicit Oily exclusion.

---

### Task 1: Add durable takeover and Release provenance schema

**Files:**
- Modify: `apps/api/control/models.py`
- Create: `apps/api/control/migrations/0015_controlled_takeover.py`
- Create: `apps/api/control/tests/test_takeover_models.py`

**Interfaces:**
- Produces `Operation.KIND_TAKEOVER_PREPARE = "service.takeover.prepare"`.
- Produces `Operation.KIND_TAKEOVER_ACTIVATE = "service.takeover.activate"`.
- Produces `ServiceTakeover` with states `queued`, `inspecting`, `preparing`, `prepared`, `activating`, `verifying`, `succeeded`, `failed`, `rolled_back`, `rollback_failed`, `canceled`.
- Produces `Release.takeover` as nullable one-to-one provenance and makes `Release.deployment` nullable.
- Enforces exactly one Release provenance source and one active takeover per Service.

- [ ] **Step 1: Write failing model constraint tests**

Create `apps/api/control/tests/test_takeover_models.py`:

```python
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from control.models import (
    Deployment,
    Project,
    Release,
    Server,
    Service,
    ServiceTakeover,
)


class TakeoverModelTests(TestCase):
    def setUp(self):
        self.server = Server.objects.create(
            name="Target",
            last_seen_at=timezone.now(),
            disk_percent=25,
        )
        self.project = Project.objects.create(name="Platform", slug="platform")
        self.service = Service.objects.create(
            project=self.project,
            name="web",
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

    def takeover(self, *, state=ServiceTakeover.STATE_QUEUED, commit="a" * 40):
        return ServiceTakeover.objects.create(
            service=self.service,
            state=state,
            requested_commit=commit,
            requested_by="operator",
            health_check_snapshot={
                "url": "http://127.0.0.1:9751/",
                "expected_status": 200,
                "attempts": 6,
                "timeout_seconds": 10,
                "interval_seconds": 5,
            },
        )

    def test_only_one_active_takeover_is_allowed_per_service(self):
        self.takeover()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.takeover(commit="b" * 40)

    def test_terminal_takeover_allows_a_new_takeover(self):
        self.takeover(state=ServiceTakeover.STATE_FAILED)
        second = self.takeover(commit="b" * 40)
        self.assertEqual(second.state, ServiceTakeover.STATE_QUEUED)

    def test_release_requires_exactly_one_provenance_source(self):
        takeover = self.takeover(state=ServiceTakeover.STATE_SUCCEEDED)
        deployment = Deployment.objects.create(
            service=self.service,
            requested_ref="main",
            resolved_commit="b" * 40,
            requested_by="operator",
            state="succeeded",
        )

        takeover_release = Release.objects.create(
            service=self.service,
            takeover=takeover,
            name="20260920-120000-aaaaaaa",
            exact_commit="a" * 40,
            path="/srv/digitalafarin/apps/platform/web/releases/20260920-120000-aaaaaaa",
        )
        self.assertIsNone(takeover_release.deployment_id)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Release.objects.create(
                    service=self.service,
                    deployment=deployment,
                    takeover=takeover,
                    name="invalid-both",
                    exact_commit="c" * 40,
                    path="/srv/digitalafarin/apps/platform/web/releases/invalid-both",
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Release.objects.create(
                    service=self.service,
                    name="invalid-neither",
                    exact_commit="d" * 40,
                    path="/srv/digitalafarin/apps/platform/web/releases/invalid-neither",
                )
```

- [ ] **Step 2: Run the new tests and verify RED**

```powershell
cd apps\api
.\.venv\Scripts\python.exe manage.py test control.tests.test_takeover_models -v 2
```

Expected: import/model failures because `ServiceTakeover` and takeover Release provenance do not exist.

- [ ] **Step 3: Add Operation kinds and `ServiceTakeover`**

In `apps/api/control/models.py`, add the two kinds to `Operation`:

```python
KIND_TAKEOVER_PREPARE = "service.takeover.prepare"
KIND_TAKEOVER_ACTIVATE = "service.takeover.activate"
```

and add to `KIND_CHOICES`:

```python
(KIND_TAKEOVER_PREPARE, "Prepare controlled service takeover"),
(KIND_TAKEOVER_ACTIVATE, "Activate controlled service takeover"),
```

Insert `ServiceTakeover` after `Deployment` and before `Release`:

```python
class ServiceTakeover(models.Model):
    STATE_QUEUED = "queued"
    STATE_INSPECTING = "inspecting"
    STATE_PREPARING = "preparing"
    STATE_PREPARED = "prepared"
    STATE_ACTIVATING = "activating"
    STATE_VERIFYING = "verifying"
    STATE_SUCCEEDED = "succeeded"
    STATE_FAILED = "failed"
    STATE_ROLLED_BACK = "rolled_back"
    STATE_ROLLBACK_FAILED = "rollback_failed"
    STATE_CANCELED = "canceled"

    ACTIVE_STATES = (
        STATE_QUEUED,
        STATE_INSPECTING,
        STATE_PREPARING,
        STATE_PREPARED,
        STATE_ACTIVATING,
        STATE_VERIFYING,
    )
    TERMINAL_STATES = (
        STATE_SUCCEEDED,
        STATE_FAILED,
        STATE_ROLLED_BACK,
        STATE_ROLLBACK_FAILED,
        STATE_CANCELED,
    )
    STATE_CHOICES = [
        (STATE_QUEUED, "Queued"),
        (STATE_INSPECTING, "Inspecting"),
        (STATE_PREPARING, "Preparing"),
        (STATE_PREPARED, "Prepared"),
        (STATE_ACTIVATING, "Activating"),
        (STATE_VERIFYING, "Verifying"),
        (STATE_SUCCEEDED, "Succeeded"),
        (STATE_FAILED, "Failed"),
        (STATE_ROLLED_BACK, "Rolled back"),
        (STATE_ROLLBACK_FAILED, "Rollback failed"),
        (STATE_CANCELED, "Canceled"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    service = models.ForeignKey(
        Service, related_name="takeovers", on_delete=models.CASCADE
    )
    state = models.CharField(
        max_length=24, choices=STATE_CHOICES, default=STATE_QUEUED
    )
    requested_commit = models.CharField(max_length=40)
    resolved_commit = models.CharField(max_length=40, blank=True)
    requested_by = models.CharField(max_length=120)

    source_snapshot = models.JSONField(default=dict, blank=True)
    source_fingerprint = models.CharField(max_length=64, blank=True)
    release_name = models.CharField(max_length=80, blank=True)
    release_path = models.CharField(max_length=500, blank=True)
    previous_current_path = models.CharField(max_length=500, null=True, blank=True)
    managed_dropin_path = models.CharField(max_length=500, blank=True)
    health_check_snapshot = models.JSONField(default=dict)

    prepare_operation = models.OneToOneField(
        Operation,
        null=True,
        blank=True,
        related_name="prepared_takeover",
        on_delete=models.SET_NULL,
    )
    activate_operation = models.OneToOneField(
        Operation,
        null=True,
        blank=True,
        related_name="activated_takeover",
        on_delete=models.SET_NULL,
    )

    failure_code = models.CharField(max_length=100, blank=True)
    failure_message = models.CharField(max_length=500, blank=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    prepared_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-queued_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["service"],
                condition=Q(state__in=ACTIVE_STATES),
                name="uniq_active_takeover_per_service",
            )
        ]
```

- [ ] **Step 4: Change `Release` provenance without breaking Deployment releases**

Replace `Release.deployment` and add `takeover`:

```python
deployment = models.OneToOneField(
    Deployment,
    null=True,
    blank=True,
    related_name="release",
    on_delete=models.PROTECT,
)
takeover = models.OneToOneField(
    ServiceTakeover,
    null=True,
    blank=True,
    related_name="release",
    on_delete=models.PROTECT,
)
```

Extend `Release.Meta.constraints`:

```python
models.CheckConstraint(
    condition=(
        Q(deployment__isnull=False, takeover__isnull=True)
        | Q(deployment__isnull=True, takeover__isnull=False)
    ),
    name="release_exactly_one_provenance",
),
```

Keep `uniq_service_release`.

- [ ] **Step 5: Generate and inspect migration `0015_controlled_takeover.py`**

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations control --name controlled_takeover
```

Verify the generated migration:
- depends on `0014_service_adoption`;
- creates `ServiceTakeover`;
- alters `Operation.kind` choices;
- makes `Release.deployment` nullable;
- adds `Release.takeover`;
- adds `release_exactly_one_provenance`;
- adds `uniq_active_takeover_per_service`.

- [ ] **Step 6: Run model tests and schema checks**

```powershell
.\.venv\Scripts\python.exe manage.py test control.tests.test_takeover_models -v 2
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py check
```

Expected: PASS and `No changes detected`.

- [ ] **Step 7: Run deployment tests to prove nullable provenance did not regress normal releases**

```powershell
.\.venv\Scripts\python.exe manage.py test control.tests.test_deployment_actions control.tests.test_deployment_state -v 2
```

Expected: PASS.

- [ ] **Step 8: Commit the schema slice**

```powershell
git add apps/api/control/models.py apps/api/control/migrations/0015_controlled_takeover.py apps/api/control/tests/test_takeover_models.py
git commit -m "feat: add controlled takeover state model"
```

---

### Task 2: Add takeover admission, prepare API, and typed PREPARE Operation

**Files:**
- Create: `apps/api/control/takeover_serializers.py`
- Create: `apps/api/control/services/takeovers.py`
- Create: `apps/api/control/takeover_views.py`
- Modify: `apps/api/control/control_urls.py`
- Modify: `apps/api/control/services/execution.py`
- Create: `apps/api/control/tests/test_takeover_api.py`

**Interfaces:**
- Produces `build_health_check_context(service) -> dict`.
- Produces `queue_takeover_prepare(service, exact_commit, requested_by) -> tuple[ServiceTakeover, Operation]`.
- Produces secret-free `ServiceTakeoverSerializer`.
- Adds `POST/GET /api/control/v1/services/<service_id>/takeovers/`.
- PREPARE Operation payload is exactly `{"takeover_id": "<uuid>"}`.

- [ ] **Step 1: Write admission/API tests**

Create `apps/api/control/tests/test_takeover_api.py` with a fixture matching the real Stage B2 configured-service shape:

```python
import os

from cryptography.fernet import Fernet
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
        self.old_keys = os.environ.get("PLATFORM_SECRET_KEYS")
        os.environ["PLATFORM_SECRET_KEYS"] = Fernet.generate_key().decode()

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
            install_configuration={
                "package_manager": "npm",
                "lockfile": "package-lock.json",
            },
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
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}"
        )

    def tearDown(self):
        if self.old_keys is None:
            os.environ.pop("PLATFORM_SECRET_KEYS", None)
        else:
            os.environ["PLATFORM_SECRET_KEYS"] = self.old_keys

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
        self.assertEqual(
            operation.payload,
            {"takeover_id": str(takeover.public_id)},
        )
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
        self.server.last_seen_at = timezone.now() - timezone.timedelta(minutes=5)
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
```

Use `from datetime import timedelta` rather than `timezone.timedelta` in the final test file:

```python
from datetime import timedelta
```

and:

```python
self.server.last_seen_at = timezone.now() - timedelta(minutes=5)
```

- [ ] **Step 2: Run API tests and verify RED**

```powershell
cd apps\api
.\.venv\Scripts\python.exe manage.py test control.tests.test_takeover_api -v 2
```

Expected: route/import failures.

- [ ] **Step 3: Make the existing health context reusable**

In `apps/api/control/services/execution.py`, rename `_health` to:

```python
def build_health_check_context(service) -> dict:
    try:
        check = service.health_check
    except ObjectDoesNotExist:
        return {
            "url": f"http://127.0.0.1:{service.service_port}/",
            "expected_status": 200,
            "attempts": 6,
            "timeout_seconds": 10,
            "interval_seconds": 5,
        }
    return {
        "url": f"http://127.0.0.1:{service.service_port}{check.path}",
        "expected_status": check.expected_status,
        "attempts": check.attempts,
        "timeout_seconds": check.timeout_seconds,
        "interval_seconds": check.interval_seconds,
    }
```

Update existing deployment/rollback contexts to call `build_health_check_context(service)`.

- [ ] **Step 4: Create strict takeover serializers**

Create `apps/api/control/takeover_serializers.py`:

```python
from rest_framework import serializers

from control.models import ServiceTakeover
from control.operation_serializers import StrictSerializer


EXACT_COMMIT_PATTERN = r"^[0-9a-f]{40}$"


class TakeoverPrepareSerializer(StrictSerializer):
    commit = serializers.RegexField(EXACT_COMMIT_PATTERN, max_length=40)


class ServiceTakeoverSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id")
    service_id = serializers.UUIDField(source="service.public_id")
    state = serializers.CharField()
    requested_commit = serializers.CharField()
    resolved_commit = serializers.CharField()
    source_fingerprint = serializers.CharField()
    source_snapshot = serializers.JSONField()
    release_name = serializers.CharField()
    release_path = serializers.CharField()
    previous_current_path = serializers.CharField(allow_null=True)
    managed_dropin_path = serializers.CharField()
    health_check_snapshot = serializers.JSONField()
    prepare_operation_id = serializers.SerializerMethodField()
    activate_operation_id = serializers.SerializerMethodField()
    failure_code = serializers.CharField()
    failure_message = serializers.CharField()
    queued_at = serializers.DateTimeField()
    prepared_at = serializers.DateTimeField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)

    def get_prepare_operation_id(self, obj):
        return (
            str(obj.prepare_operation.public_id)
            if obj.prepare_operation_id
            else None
        )

    def get_activate_operation_id(self, obj):
        return (
            str(obj.activate_operation.public_id)
            if obj.activate_operation_id
            else None
        )
```

Do not expose environment values or Agent execution context.

- [ ] **Step 5: Implement prepare admission and queueing**

Create `apps/api/control/services/takeovers.py` with the domain error and prepare queue:

```python
from django.db import IntegrityError, transaction

from control.models import (
    AuditEvent,
    Operation,
    Service,
    ServiceTakeover,
)
from control.services.execution import build_health_check_context
from control.services.operations import create_operation


class TakeoverError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _require_prepare_eligible(service: Service) -> bool:
    if service.lifecycle_state != Service.LIFECYCLE_CONFIGURED:
        raise TakeoverError(
            "service_not_configured",
            "Service must be configured before controlled takeover.",
        )
    if service.executor != Service.EXECUTOR_SYSTEMD:
        raise TakeoverError(
            "unsupported_takeover_runtime",
            "Controlled takeover requires systemd.",
        )
    if service.runtime != Service.RUNTIME_NODE:
        raise TakeoverError(
            "unsupported_takeover_runtime",
            "Stage B3 supports node-nextjs only.",
        )
    required = {
        "repository": service.repository,
        "root_directory": service.root_directory,
        "service_port": service.service_port,
        "unit_name": service.unit_name,
    }
    if any(value in {None, ""} for value in required.values()):
        raise TakeoverError(
            "service_configuration_incomplete",
            "Service deployment metadata is incomplete.",
        )
    if not service.target_server.services.filter(
        unit_name=service.unit_name
    ).exists():
        raise TakeoverError(
            "inventory_unit_missing",
            "Configured systemd unit is missing from current inventory.",
        )
    if service.target_server.status != "online":
        raise TakeoverError(
            "server_offline",
            "Target server must have fresh telemetry.",
        )
    if service.target_server.disk_percent >= 90:
        raise TakeoverError(
            "disk_usage_blocked",
            "Disk usage blocks controlled takeover.",
        )
    return service.target_server.disk_percent >= 80


@transaction.atomic
def queue_takeover_prepare(
    *,
    service: Service,
    exact_commit: str,
    requested_by: str,
) -> tuple[ServiceTakeover, Operation]:
    warning = _require_prepare_eligible(service)
    if ServiceTakeover.objects.filter(
        service=service,
        state__in=ServiceTakeover.ACTIVE_STATES,
    ).exists():
        raise TakeoverError(
            "takeover_already_active",
            "A controlled takeover is already active for this service.",
        )

    try:
        takeover = ServiceTakeover.objects.create(
            service=service,
            requested_commit=exact_commit,
            requested_by=requested_by,
            health_check_snapshot=build_health_check_context(service),
        )
    except IntegrityError as exc:
        raise TakeoverError(
            "takeover_already_active",
            "A controlled takeover is already active for this service.",
        ) from exc

    operation = create_operation(
        server=service.target_server,
        kind=Operation.KIND_TAKEOVER_PREPARE,
        payload={"takeover_id": str(takeover.public_id)},
        actor=requested_by,
    )
    takeover.prepare_operation = operation
    takeover.save(update_fields=["prepare_operation", "updated_at"])

    AuditEvent.objects.create(
        event_type="service.takeover.requested",
        target_type="service_takeover",
        target_id=str(takeover.public_id),
        actor=requested_by,
        metadata={
            "service_id": str(service.public_id),
            "server_id": str(service.target_server.public_id),
            "unit_name": service.unit_name,
            "exact_commit": exact_commit,
            "disk_warning": warning,
        },
    )
    return takeover, operation
```

- [ ] **Step 6: Add prepare/history view and routes**

Create `apps/api/control/takeover_views.py` with `ServiceTakeoverListCreateView`:

```python
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.models import Service
from control.permissions import require_scope
from control.services.takeovers import TakeoverError, queue_takeover_prepare
from control.takeover_serializers import (
    ServiceTakeoverSerializer,
    TakeoverPrepareSerializer,
)


def _takeover_error(exc: TakeoverError):
    return Response(
        {"error": exc.code, "message": str(exc)},
        status=status.HTTP_409_CONFLICT,
    )


class ServiceTakeoverListCreateView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]

    def get_permissions(self):
        scope = (
            "operations:create"
            if self.request.method == "POST"
            else "operations:read"
        )
        return [require_scope(scope)()]

    def _service(self, service_id):
        try:
            return Service.objects.select_related(
                "project", "target_server"
            ).get(public_id=service_id)
        except Service.DoesNotExist:
            return None

    def get(self, request, service_id):
        service = self._service(service_id)
        if service is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "items": ServiceTakeoverSerializer(
                    service.takeovers.select_related(
                        "service", "prepare_operation", "activate_operation"
                    ).all(),
                    many=True,
                ).data
            }
        )

    def post(self, request, service_id):
        service = self._service(service_id)
        if service is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = TakeoverPrepareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            takeover, _operation = queue_takeover_prepare(
                service=service,
                exact_commit=serializer.validated_data["commit"],
                requested_by=request.user.name,
            )
        except TakeoverError as exc:
            return _takeover_error(exc)

        return Response(
            ServiceTakeoverSerializer(takeover).data,
            status=status.HTTP_201_CREATED,
        )
```

Add to `apps/api/control/control_urls.py`:

```python
from control import takeover_views
```

and:

```python
path(
    "services/<uuid:service_id>/takeovers/",
    takeover_views.ServiceTakeoverListCreateView.as_view(),
),
```

- [ ] **Step 7: Run API tests**

```powershell
.\.venv\Scripts\python.exe manage.py test control.tests.test_takeover_api -v 2
```

Expected: PASS for prepare/history admission tests.

- [ ] **Step 8: Commit the admission/API slice**

```powershell
git add apps/api/control/takeover_serializers.py apps/api/control/services/takeovers.py apps/api/control/takeover_views.py apps/api/control/control_urls.py apps/api/control/services/execution.py apps/api/control/tests/test_takeover_api.py
git commit -m "feat: queue controlled takeover preparation"
```

---

### Task 3: Add Agent PREPARE execution context and durable prepared-result handling

**Files:**
- Modify: `apps/api/control/services/execution.py`
- Modify: `apps/api/control/services/takeovers.py`
- Modify: `apps/api/control/agent_views.py`
- Create: `apps/api/control/tests/test_takeover_results.py`

**Interfaces:**
- `build_execution_context()` produces a server-derived PREPARE context with no caller-controlled path/unit.
- `mark_takeover_operation_started(operation)` is idempotent.
- `apply_takeover_result(operation, succeeded, result, error_code, error_message)` is idempotent.
- A successful PREPARE completion persists snapshot/fingerprint/release metadata and moves takeover to `prepared`.

- [ ] **Step 1: Write failing Agent claim/start/completion tests**

Create `apps/api/control/tests/test_takeover_results.py`. Reuse authenticated Agent setup and add these focused tests:

```python
import os

from cryptography.fernet import Fernet
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import (
    AgentCredential,
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
from control.services.takeovers import queue_takeover_prepare


class TakeoverResultTests(TestCase):
    def setUp(self):
        self.old_keys = os.environ.get("PLATFORM_SECRET_KEYS")
        os.environ["PLATFORM_SECRET_KEYS"] = Fernet.generate_key().decode()

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
        service_secret = issue_secret("service")
        ServiceCredential.objects.create(
            principal=principal,
            token_prefix=service_secret.prefix,
            token_hash=service_secret.digest,
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

    def tearDown(self):
        if self.old_keys is None:
            os.environ.pop("PLATFORM_SECRET_KEYS", None)
        else:
            os.environ["PLATFORM_SECRET_KEYS"] = self.old_keys

    def claim(self):
        return self.agent.post(
            "/api/agent/v1/operations/claim", {}, format="json"
        ).json()

    def test_prepare_claim_context_is_server_derived_and_secret_free(self):
        claim = self.claim()
        execution = claim["operation"]["execution"]

        self.assertEqual(execution["takeover_id"], str(self.takeover.public_id))
        self.assertEqual(
            execution["unit_name"],
            "digitalafarin-platform-web.service",
        )
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
        self.assertEqual(
            self.takeover.state,
            ServiceTakeover.STATE_INSPECTING,
        )

        snapshot = {
            "unit_name": self.service.unit_name,
            "fragment_path": "/etc/systemd/system/digitalafarin-platform-web.service",
            "drop_in_paths": [],
            "user": "deploy",
            "group": "www-data",
            "working_directory": "/opt/digitalafarin-platform/apps/web",
            "exec_start_path": "/usr/bin/npm",
            "exec_start_argv": ["/usr/bin/npm", "start", "--", "--hostname", "127.0.0.1", "--port", "9751"],
            "environment_file_paths": ["/etc/digitalafarin-platform/web.env"],
            "restart_policy": "on-failure",
            "restart_delay_usec": 3_000_000,
            "source_file_hashes": [
                {
                    "path": "/etc/systemd/system/digitalafarin-platform-web.service",
                    "sha256": "1" * 64,
                }
            ],
        }
        result = {
            "takeover_id": str(self.takeover.public_id),
            "final_state": "prepared",
            "resolved_commit": "a" * 40,
            "source_snapshot": snapshot,
            "source_fingerprint": "2" * 64,
            "release_name": "20260920-120000-aaaaaaa",
            "release_path": "/srv/digitalafarin/apps/digitalafarin-platform/platform-web/releases/20260920-120000-aaaaaaa",
            "events": [
                {"state": "inspecting", "message": ""},
                {"state": "preparing", "message": ""},
                {"state": "prepared", "message": ""},
            ],
        }

        completed = self.agent.post(
            f"/api/agent/v1/operations/{operation_id}/complete",
            {
                "claim_token": token,
                "succeeded": True,
                "result": result,
            },
            format="json",
        )
        self.assertEqual(completed.status_code, 200)

        self.takeover.refresh_from_db()
        self.assertEqual(self.takeover.state, ServiceTakeover.STATE_PREPARED)
        self.assertEqual(self.takeover.source_snapshot["user"], "deploy")
        self.assertEqual(self.takeover.source_fingerprint, "2" * 64)
        self.assertEqual(
            self.takeover.release_name,
            "20260920-120000-aaaaaaa",
        )
        self.assertEqual(
            self.service.lifecycle_state,
            Service.LIFECYCLE_CONFIGURED,
        )
```

Also add the review-focus retry test using the domain function directly:

```python
def test_reapplying_same_prepare_result_is_idempotent(self):
    from control.services.takeovers import apply_takeover_result

    result = {
        "takeover_id": str(self.takeover.public_id),
        "final_state": "prepared",
        "resolved_commit": "a" * 40,
        "source_snapshot": {
            "unit_name": self.service.unit_name,
            "fragment_path": "/etc/systemd/system/unit.service",
            "drop_in_paths": [],
            "user": "deploy",
            "group": "www-data",
            "working_directory": "/opt/app",
            "exec_start_path": "/usr/bin/npm",
            "exec_start_argv": ["/usr/bin/npm", "start"],
            "environment_file_paths": [],
            "restart_policy": "on-failure",
            "restart_delay_usec": 3_000_000,
            "source_file_hashes": [],
        },
        "source_fingerprint": "2" * 64,
        "release_name": "20260920-120000-aaaaaaa",
        "release_path": "/srv/digitalafarin/apps/digitalafarin-platform/platform-web/releases/20260920-120000-aaaaaaa",
        "events": [
            {"state": "inspecting", "message": ""},
            {"state": "preparing", "message": ""},
            {"state": "prepared", "message": ""},
        ],
    }

    apply_takeover_result(
        self.operation,
        succeeded=True,
        result=result,
        error_code="",
        error_message="",
    )
    apply_takeover_result(
        self.operation,
        succeeded=True,
        result=result,
        error_code="",
        error_message="",
    )

    self.takeover.refresh_from_db()
    self.assertEqual(self.takeover.state, ServiceTakeover.STATE_PREPARED)
```

- [ ] **Step 2: Run and verify RED**

```powershell
cd apps\api
.\.venv\Scripts\python.exe manage.py test control.tests.test_takeover_results -v 2
```

Expected: missing takeover execution/result hooks.

- [ ] **Step 3: Add PREPARE execution context**

Extend `build_execution_context()` in `apps/api/control/services/execution.py`:

```python
from control.models import (
    DatabaseResource,
    Deployment,
    Domain,
    Operation,
    Release,
    ServiceTakeover,
)
```

Add before `return None`:

```python
if operation.kind == Operation.KIND_TAKEOVER_PREPARE:
    takeover = ServiceTakeover.objects.select_related(
        "service__project",
        "service__target_server",
    ).get(
        public_id=operation.payload["takeover_id"],
        service__target_server=operation.server,
    )
    service = takeover.service
    return {
        "takeover_id": str(takeover.public_id),
        "service_id": str(service.public_id),
        "project_slug": service.project.slug,
        "service_name": service.name,
        "unit_name": service.unit_name,
        "repository": service.repository,
        "exact_commit": takeover.requested_commit,
        "runtime": service.runtime,
        "root_directory": service.root_directory,
        "install_configuration": service.install_configuration,
        "build_configuration": service.build_configuration,
        "service_port": service.service_port,
        "health_check": takeover.health_check_snapshot,
    }
```

No environment value, caller path, or caller unit is read from `Operation.payload`.

- [ ] **Step 4: Add started/result state hooks**

In `apps/api/control/services/takeovers.py`, define a transition map and idempotent state helper:

```python
TAKEOVER_NEXT_STATES = {
    ServiceTakeover.STATE_QUEUED: {
        ServiceTakeover.STATE_INSPECTING,
        ServiceTakeover.STATE_FAILED,
    },
    ServiceTakeover.STATE_INSPECTING: {
        ServiceTakeover.STATE_PREPARING,
        ServiceTakeover.STATE_FAILED,
    },
    ServiceTakeover.STATE_PREPARING: {
        ServiceTakeover.STATE_PREPARED,
        ServiceTakeover.STATE_FAILED,
    },
    ServiceTakeover.STATE_PREPARED: {
        ServiceTakeover.STATE_ACTIVATING,
        ServiceTakeover.STATE_CANCELED,
    },
    ServiceTakeover.STATE_ACTIVATING: {
        ServiceTakeover.STATE_VERIFYING,
        ServiceTakeover.STATE_FAILED,
        ServiceTakeover.STATE_ROLLED_BACK,
        ServiceTakeover.STATE_ROLLBACK_FAILED,
    },
    ServiceTakeover.STATE_VERIFYING: {
        ServiceTakeover.STATE_SUCCEEDED,
        ServiceTakeover.STATE_FAILED,
        ServiceTakeover.STATE_ROLLED_BACK,
        ServiceTakeover.STATE_ROLLBACK_FAILED,
    },
}
```

Implement:

```python
@transaction.atomic
def transition_takeover(
    takeover_id,
    new_state: str,
    *,
    actor: str,
    failure_code: str = "",
    failure_message: str = "",
) -> ServiceTakeover:
    takeover = ServiceTakeover.objects.select_for_update().select_related(
        "service"
    ).get(public_id=takeover_id)

    if takeover.state == new_state:
        return takeover

    if new_state not in TAKEOVER_NEXT_STATES.get(takeover.state, set()):
        raise TakeoverError(
            "invalid_takeover_transition",
            f"Illegal takeover transition: {takeover.state} -> {new_state}",
        )

    previous = takeover.state
    now = timezone.now()
    takeover.state = new_state
    if new_state in {
        ServiceTakeover.STATE_INSPECTING,
        ServiceTakeover.STATE_ACTIVATING,
    } and takeover.started_at is None:
        takeover.started_at = now
    if new_state == ServiceTakeover.STATE_PREPARED:
        takeover.prepared_at = now
    if new_state in ServiceTakeover.TERMINAL_STATES:
        takeover.completed_at = now
        takeover.failure_code = failure_code[:100]
        takeover.failure_message = failure_message[:500]

    takeover.save()

    AuditEvent.objects.create(
        event_type=f"service.takeover.{new_state}",
        target_type="service_takeover",
        target_id=str(takeover.public_id),
        actor=actor,
        metadata={
            "service_id": str(takeover.service.public_id),
            "from_state": previous,
            "to_state": new_state,
        },
    )
    return takeover
```

Add:

```python
def mark_takeover_operation_started(operation: Operation) -> None:
    if operation.kind == Operation.KIND_TAKEOVER_PREPARE:
        takeover = ServiceTakeover.objects.get(
            public_id=operation.payload["takeover_id"]
        )
        if takeover.state == ServiceTakeover.STATE_QUEUED:
            transition_takeover(
                takeover.public_id,
                ServiceTakeover.STATE_INSPECTING,
                actor=operation.actor,
            )
```

Then implement PREPARE result validation in `apply_takeover_result(...)`:
- lock takeover by `operation.payload["takeover_id"]`;
- if `succeeded=False`, transition nonterminal takeover to `failed`;
- require `final_state == "prepared"`;
- require matching `takeover_id`;
- require `resolved_commit == requested_commit`;
- require 64 lowercase hex fingerprint;
- require safe release name `^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}(?:-[0-9]+)?$`;
- derive expected release path from project/service/release name and reject mismatches;
- require snapshot keys exactly equal to the non-secret contract;
- transition through `preparing` then `prepared`;
- persist snapshot/fingerprint/release fields before `prepared`;
- if already `prepared` with identical fields, return without duplicate mutation.

Use:

```python
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
RELEASE_NAME_RE = re.compile(
    r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}(?:-[0-9]+)?$"
)
```

- [ ] **Step 5: Wire hooks into Agent operation start/completion**

In `apps/api/control/agent_views.py` import:

```python
from control.services.takeovers import (
    TakeoverError,
    apply_takeover_result,
    mark_takeover_operation_started,
)
```

In `OperationStartedView.post`, after `start_operation(...)`:

```python
mark_takeover_operation_started(operation)
```

In `OperationCompleteView.post`, before `complete_operation(...)`:

```python
if operation_record.kind in {
    Operation.KIND_TAKEOVER_PREPARE,
    Operation.KIND_TAKEOVER_ACTIVATE,
}:
    apply_takeover_result(
        operation_record,
        succeeded=serializer.validated_data["succeeded"],
        result=serializer.validated_data.get("result", {}),
        error_code=serializer.validated_data.get("error_code", ""),
        error_message=serializer.validated_data.get("error_message", ""),
    )
```

Catch `TakeoverError` alongside `OperationTransitionError` and return `409` with a bounded error body.

- [ ] **Step 6: Run the result tests and existing deployment completion tests**

```powershell
.\.venv\Scripts\python.exe manage.py test control.tests.test_takeover_results control.tests.test_deployment_actions -v 2
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add apps/api/control/services/execution.py apps/api/control/services/takeovers.py apps/api/control/agent_views.py apps/api/control/tests/test_takeover_results.py
git commit -m "feat: persist prepared takeover results"
```

---

### Task 4: Add stable systemd inspection, fingerprinting, and release runner injection

**Files:**
- Create: `agent/digitalafarin_agent/takeover_systemd.py`
- Modify: `agent/digitalafarin_agent/releases.py`
- Create: `agent/tests/test_takeover_systemd.py`
- Modify: `agent/tests/test_release_engine.py`

**Interfaces:**
- Produces `inspect_service(unit_name) -> dict`.
- Produces `fingerprint_snapshot(snapshot) -> str`.
- Produces `managed_dropin_path(unit_name) -> Path`.
- Produces `write_managed_dropin(unit_name, working_directory) -> Path`, `remove_managed_dropin(unit_name)`, `daemon_reload()`, `restart_takeover_unit(unit_name)`.
- `prepare_release(..., run_command=_run)` permits takeover to inject non-root Git execution while all current callers keep existing behavior.

- [ ] **Step 1: Write fingerprint safety tests**

Create `agent/tests/test_takeover_systemd.py`:

```python
from pathlib import Path

import pytest

from digitalafarin_agent.takeover_systemd import (
    TakeoverSystemdError,
    fingerprint_snapshot,
    inspect_service,
    managed_dropin_path,
)


def show_output(start_time: str, pid: str) -> str:
    return "\n".join(
        [
            "FragmentPath=/etc/systemd/system/digitalafarin-platform-web.service",
            "DropInPaths=",
            "User=deploy",
            "Group=www-data",
            "WorkingDirectory=/opt/digitalafarin-platform/apps/web",
            (
                "ExecStart={ path=/usr/bin/npm ; "
                "argv[]=/usr/bin/npm start -- --hostname 127.0.0.1 --port 9751 ; "
                f"ignore_errors=no ; start_time=[{start_time}] ; "
                f"stop_time=[n/a] ; pid={pid} ; code=(null) ; status=0/0 }}"
            ),
            "EnvironmentFiles=/etc/digitalafarin-platform/web.env (ignore_errors=no)",
            "Restart=on-failure",
            "RestartUSec=3s",
        ]
    )


def test_fingerprint_ignores_execstart_runtime_pid_and_start_time(tmp_path, monkeypatch):
    unit = tmp_path / "digitalafarin-platform-web.service"
    unit.write_text("[Service]\nExecStart=/usr/bin/npm start\n", encoding="utf-8")

    outputs = iter(
        [
            show_output("Sun 2026-09-20 15:18:27 +0330", "517797"),
            show_output("Sun 2026-09-20 16:00:00 +0330", "600001"),
        ]
    )

    def run(*_args, **_kwargs):
        class Result:
            stdout = next(outputs)
        return Result()

    monkeypatch.setattr(
        "digitalafarin_agent.takeover_systemd.subprocess.run",
        run,
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_systemd._read_hash",
        lambda path: "a" * 64,
    )

    first = inspect_service(
        "digitalafarin-platform-web.service",
        fragment_override=unit,
    )
    second = inspect_service(
        "digitalafarin-platform-web.service",
        fragment_override=unit,
    )

    assert first["exec_start_path"] == "/usr/bin/npm"
    assert first["exec_start_argv"] == [
        "/usr/bin/npm",
        "start",
        "--",
        "--hostname",
        "127.0.0.1",
        "--port",
        "9751",
    ]
    assert fingerprint_snapshot(first) == fingerprint_snapshot(second)


def test_fingerprint_changes_when_source_file_hash_changes():
    base = {
        "unit_name": "digitalafarin-platform-web.service",
        "fragment_path": "/etc/systemd/system/digitalafarin-platform-web.service",
        "drop_in_paths": [],
        "user": "deploy",
        "group": "www-data",
        "working_directory": "/opt/app",
        "exec_start_path": "/usr/bin/npm",
        "exec_start_argv": ["/usr/bin/npm", "start"],
        "environment_file_paths": [],
        "restart_policy": "on-failure",
        "restart_delay_usec": 3_000_000,
        "source_file_hashes": [
            {"path": "/etc/systemd/system/unit.service", "sha256": "a" * 64}
        ],
    }
    changed = {
        **base,
        "source_file_hashes": [
            {"path": "/etc/systemd/system/unit.service", "sha256": "b" * 64}
        ],
    }

    assert fingerprint_snapshot(base) != fingerprint_snapshot(changed)


def test_managed_dropin_path_is_derived_from_valid_unit_only():
    assert managed_dropin_path(
        "digitalafarin-platform-web.service"
    ) == Path(
        "/etc/systemd/system/"
        "digitalafarin-platform-web.service.d/"
        "90-digitalafarin-managed.conf"
    )

    with pytest.raises(TakeoverSystemdError):
        managed_dropin_path("../../etc/passwd")
```

- [ ] **Step 2: Write release runner injection test**

Append to `agent/tests/test_release_engine.py`:

```python
def test_prepare_release_uses_injected_runner_for_git_commands(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    apps = tmp_path / "apps"
    commit = "a" * 40
    calls = []

    def runner(argv, timeout=300):
        calls.append((argv, timeout))
        destination = Path(argv[-1]) if argv[:2] == ["git", "clone"] else None
        if destination is not None:
            destination.mkdir(parents=True)

    release = prepare_release(
        "platform",
        "web",
        str(repo),
        commit,
        apps_root=apps,
        timestamp="20260920-120000",
        run_command=runner,
    )

    assert release.name == "20260920-120000-aaaaaaa"
    assert calls[0][0][:3] == ["git", "clone", "--no-checkout"]
    assert calls[1][0][0:3] == ["git", "-C", str(release)]
```

- [ ] **Step 3: Run Agent tests and verify RED**

From WSL/Ubuntu for POSIX-sensitive tests:

```bash
cd "/mnt/d/projects/next-drf projects/digitalafarin-platform/agent"
source /tmp/da-agent-b3-venv/bin/activate 2>/dev/null || true
python3 -m pytest -q tests/test_takeover_systemd.py tests/test_release_engine.py
```

If the B3 venv does not exist yet:

```bash
python3 -m venv /tmp/da-agent-b3-venv
source /tmp/da-agent-b3-venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_takeover_systemd.py tests/test_release_engine.py
```

Expected: missing module/signature failures.

- [ ] **Step 4: Add injected runner to `prepare_release`**

Change signature in `agent/digitalafarin_agent/releases.py`:

```python
def prepare_release(
    project_slug: str,
    service_name: str,
    repository: str,
    exact_commit: str,
    *,
    apps_root: Path = Path("/srv/digitalafarin/apps"),
    timestamp: str | None = None,
    run_command=_run,
) -> Path:
```

Replace the two direct `_run(...)` calls with:

```python
run_command(
    ["git", "clone", "--no-checkout", "--", repository, str(release)],
    timeout=300,
)
run_command(
    ["git", "-C", str(release), "checkout", "--detach", exact_commit],
    timeout=300,
)
```

Do not alter existing call sites; the default preserves current deployment behavior.

- [ ] **Step 5: Implement stable systemd inspection**

Create `agent/digitalafarin_agent/takeover_systemd.py` with:
- unit regex identical in strength to existing safe unit validation;
- one fixed `systemctl show` argv requesting only the required properties;
- `ExecStart` parser that extracts only `path=` and `argv[]=` and discards runtime fields;
- environment-file path parser that strips `(ignore_errors=...)`;
- SHA-256 hashes for fragment and every drop-in file;
- canonical `json.dumps(..., sort_keys=True, separators=(",", ":"))` fingerprint.

Core signatures:

```python
def inspect_service(
    unit_name: str,
    *,
    fragment_override: Path | None = None,
) -> dict:
    ...

def fingerprint_snapshot(snapshot: dict) -> str:
    canonical = json.dumps(
        snapshot,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

The snapshot keys must be exactly:

```python
{
    "unit_name",
    "fragment_path",
    "drop_in_paths",
    "user",
    "group",
    "working_directory",
    "exec_start_path",
    "exec_start_argv",
    "environment_file_paths",
    "restart_policy",
    "restart_delay_usec",
    "source_file_hashes",
}
```

Reject missing/non-file fragment paths and unreadable declared drop-ins with `TakeoverSystemdError`.

- [ ] **Step 6: Add derived mutation helpers without weakening generic protection**

In the same module implement:

```python
MANAGED_DROPIN_NAME = "90-digitalafarin-managed.conf"
SYSTEMD_ROOT = Path("/etc/systemd/system")


def managed_dropin_path(unit_name: str) -> Path:
    # validate unit, derive only under SYSTEMD_ROOT
    ...


def write_managed_dropin(
    unit_name: str,
    working_directory: Path,
    *,
    systemd_root: Path = SYSTEMD_ROOT,
) -> Path:
    # create .d, fail if reserved final path already exists,
    # write same-directory temp, chmod 0644, chown root:root,
    # os.replace(temp, final)
    ...


def remove_managed_dropin(
    unit_name: str,
    *,
    systemd_root: Path = SYSTEMD_ROOT,
) -> None:
    ...


def daemon_reload() -> None:
    subprocess.run(
        ["systemctl", "daemon-reload"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
    )


def restart_takeover_unit(unit_name: str) -> None:
    # validate exact service syntax but intentionally do not call
    # SystemdExecutor.restart(), whose protected-unit block stays unchanged.
    subprocess.run(
        ["systemctl", "restart", unit_name],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
    )
```

`restart_takeover_unit` is imported only by the takeover orchestrator and never exposed as a generic operation.

- [ ] **Step 7: Run tests**

```bash
python -m pytest -q tests/test_takeover_systemd.py tests/test_release_engine.py tests/test_systemd_executor.py
```

Expected: PASS, including the existing protected generic executor behavior.

- [ ] **Step 8: Commit**

```bash
git add agent/digitalafarin_agent/releases.py agent/digitalafarin_agent/takeover_systemd.py agent/tests/test_takeover_systemd.py agent/tests/test_release_engine.py
git commit -m "feat: inspect and fingerprint takeover systemd units"
```

---

### Task 5: Implement non-mutating Agent PREPARE as the source service user

**Files:**
- Create: `agent/digitalafarin_agent/takeover.py`
- Modify: `agent/digitalafarin_agent/operations.py`
- Create: `agent/tests/test_takeover.py`
- Modify: `agent/tests/test_operations.py`

**Interfaces:**
- Produces `prepare_service_takeover(payload, apps_root=...) -> dict`.
- Produces `run_as_user(user, argv, cwd=None, timeout=...)`.
- Dispatches only `service.takeover.prepare` to PREPARE.
- PREPARE returns snapshot/fingerprint/release metadata/events but performs no activation or service mutation.

- [ ] **Step 1: Write PREPARE behavior tests**

Create `agent/tests/test_takeover.py` beginning with:

```python
from pathlib import Path

import pytest

from digitalafarin_agent.takeover import (
    TakeoverExecutionError,
    prepare_service_takeover,
)


def prepare_payload():
    return {
        "takeover_id": "11111111-1111-1111-1111-111111111111",
        "service_id": "22222222-2222-2222-2222-222222222222",
        "project_slug": "digitalafarin-platform",
        "service_name": "platform-web",
        "unit_name": "digitalafarin-platform-web.service",
        "repository": "https://github.com/example/platform.git",
        "exact_commit": "a" * 40,
        "runtime": "node-nextjs",
        "root_directory": "apps/web",
        "install_configuration": {
            "package_manager": "npm",
            "lockfile": "package-lock.json",
        },
        "build_configuration": {"build_script": "build"},
        "service_port": 9751,
        "health_check": {
            "url": "http://127.0.0.1:9751/",
            "expected_status": 200,
            "attempts": 6,
            "timeout_seconds": 10,
            "interval_seconds": 5,
        },
    }


def snapshot(user="deploy"):
    return {
        "unit_name": "digitalafarin-platform-web.service",
        "fragment_path": "/etc/systemd/system/digitalafarin-platform-web.service",
        "drop_in_paths": [],
        "user": user,
        "group": "www-data",
        "working_directory": "/opt/digitalafarin-platform/apps/web",
        "exec_start_path": "/usr/bin/npm",
        "exec_start_argv": [
            "/usr/bin/npm", "start", "--",
            "--hostname", "127.0.0.1", "--port", "9751",
        ],
        "environment_file_paths": [
            "/etc/digitalafarin-platform/web.env"
        ],
        "restart_policy": "on-failure",
        "restart_delay_usec": 3_000_000,
        "source_file_hashes": [
            {
                "path": "/etc/systemd/system/digitalafarin-platform-web.service",
                "sha256": "1" * 64,
            }
        ],
    }


def test_prepare_builds_release_as_source_user_without_activation(
    tmp_path,
    monkeypatch,
):
    calls = []
    release = (
        tmp_path
        / "apps"
        / "digitalafarin-platform"
        / "platform-web"
        / "releases"
        / "20260920-120000-aaaaaaa"
    )
    (release / "apps" / "web" / ".next").mkdir(parents=True)
    (release / "apps" / "web" / "package.json").write_text("{}", encoding="utf-8")
    (release / "apps" / "web" / "package-lock.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "digitalafarin_agent.takeover.inspect_service",
        lambda _unit: snapshot(),
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot",
        lambda _snapshot: "2" * 64,
    )

    def fake_prepare(*_args, **kwargs):
        calls.append(("git_user", kwargs["run_command"]))
        return release

    monkeypatch.setattr(
        "digitalafarin_agent.takeover.prepare_release",
        fake_prepare,
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.run_recipe_as_user",
        lambda user, commands, cwd: calls.append(
            ("build", user, commands, cwd)
        ),
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.managed_dropin_path",
        lambda _unit: tmp_path / "not-present.conf",
    )

    result = prepare_service_takeover(
        prepare_payload(),
        apps_root=tmp_path / "apps",
    )

    assert result["final_state"] == "prepared"
    assert result["source_fingerprint"] == "2" * 64
    assert result["release_name"] == release.name
    assert calls[1][1] == "deploy"
    assert calls[1][3] == release / "apps" / "web"


@pytest.mark.parametrize("user", ["", "root"])
def test_prepare_rejects_unsafe_source_user_before_build(
    tmp_path,
    monkeypatch,
    user,
):
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.inspect_service",
        lambda _unit: snapshot(user=user),
    )

    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("build path must not run")

    monkeypatch.setattr(
        "digitalafarin_agent.takeover.prepare_release",
        fail_if_called,
    )

    with pytest.raises(TakeoverExecutionError) as exc:
        prepare_service_takeover(
            prepare_payload(),
            apps_root=tmp_path / "apps",
        )

    assert exc.value.code == "source_user_unsafe"
    assert called is False
```

Add a test that makes `managed_dropin_path(unit).exists()` true and expects `managed_dropin_conflict` before clone/build.

Add a path-escape test using `root_directory="../outside"` and expect `release_validation_failed`.

- [ ] **Step 2: Run PREPARE tests and verify RED**

```bash
cd "/mnt/d/projects/next-drf projects/digitalafarin-platform/agent"
source /tmp/da-agent-b3-venv/bin/activate
python -m pytest -q tests/test_takeover.py
```

- [ ] **Step 3: Implement run-as-user primitives**

In `agent/digitalafarin_agent/takeover.py`:

```python
import os
import pwd
import re
import subprocess
from pathlib import Path

from .executors.systemd import SystemdExecutor
from .releases import prepare_release
from .takeover_systemd import (
    fingerprint_snapshot,
    inspect_service,
    managed_dropin_path,
)


SAFE_ROOT = re.compile(
    r"^(?:\.|[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)$"
)


class TakeoverExecutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _account(user: str):
    if not user or user == "root":
        raise TakeoverExecutionError(
            "source_user_unsafe",
            "Takeover build requires a non-root source service user.",
        )
    try:
        return pwd.getpwnam(user)
    except KeyError as exc:
        raise TakeoverExecutionError(
            "source_user_unsafe",
            "Source service user does not exist.",
        ) from exc


def run_as_user(
    user: str,
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 900,
) -> None:
    account = _account(user)
    result = subprocess.run(
        [
            "runuser",
            "-u",
            user,
            "--",
            "env",
            f"HOME={account.pw_dir}",
            *argv,
        ],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )
    if result.returncode != 0:
        raise TakeoverExecutionError(
            "release_prepare_failed",
            "Takeover build command failed.",
        )


def run_recipe_as_user(
    user: str,
    commands: list[list[str]],
    cwd: Path,
) -> None:
    for command in commands:
        run_as_user(user, command, cwd=cwd, timeout=900)
```

Do not pass runtime secret values to PREPARE build commands.

- [ ] **Step 4: Implement PREPARE orchestration**

`prepare_service_takeover(...)` must:
1. reject unexpected payload keys;
2. require exact 40-char SHA and `runtime == "node-nextjs"`;
3. inspect source service and require snapshot unit equals context unit;
4. reject unsafe source user;
5. reject an already-existing reserved managed drop-in;
6. derive `service_root` only from `apps_root/project_slug/service_name`;
7. create/chown only `service_root/releases` and `service_root/shared` to the source user/group so Git can create the release;
8. inject `run_as_user` into `prepare_release`;
9. derive/validate `root_directory` under the release;
10. obtain Node recipe from `SystemdExecutor.recipe_commands(...)`;
11. run recipe as source user;
12. require `package.json`, configured lockfile `package-lock.json`, and `.next/`;
13. return the exact non-secret result contract.

Result:

```python
{
    "takeover_id": payload["takeover_id"],
    "final_state": "prepared",
    "resolved_commit": payload["exact_commit"],
    "source_snapshot": source_snapshot,
    "source_fingerprint": fingerprint_snapshot(source_snapshot),
    "release_name": release.name,
    "release_path": str(release),
    "events": [
        {"state": "inspecting", "message": ""},
        {"state": "preparing", "message": ""},
        {"state": "prepared", "message": ""},
    ],
}
```

- [ ] **Step 5: Dispatch typed PREPARE without exposing generic restart**

In `agent/digitalafarin_agent/operations.py`:

```python
from .takeover import (
    TakeoverExecutionError,
    prepare_service_takeover,
)
```

Add before generic service actions:

```python
if kind == "service.takeover.prepare":
    try:
        return prepare_service_takeover(payload)
    except TakeoverExecutionError as exc:
        raise OperationExecutionError(exc.code, str(exc)) from exc
```

Do not add `service.takeover.prepare` to `SERVICE_ACTIONS`.

- [ ] **Step 6: Add dispatch/protection test**

Append to `agent/tests/test_operations.py`:

```python
def test_takeover_prepare_uses_dedicated_executor_and_generic_protection_remains(
    monkeypatch,
):
    monkeypatch.setattr(
        "digitalafarin_agent.operations.prepare_service_takeover",
        lambda payload: {"takeover_id": payload["takeover_id"], "final_state": "prepared"},
    )

    result = execute_operation(
        "service.takeover.prepare",
        {"takeover_id": "11111111-1111-1111-1111-111111111111"},
    )
    assert result["final_state"] == "prepared"

    with pytest.raises(OperationExecutionError) as exc:
        execute_operation(
            "service.restart",
            {"unit_name": "digitalafarin-platform-web.service"},
        )
    assert exc.value.code == "protected_unit"
```

- [ ] **Step 7: Run PREPARE and operations tests**

```bash
python -m pytest -q tests/test_takeover.py tests/test_operations.py tests/test_systemd_executor.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add agent/digitalafarin_agent/takeover.py agent/digitalafarin_agent/operations.py agent/tests/test_takeover.py agent/tests/test_operations.py
git commit -m "feat: prepare takeover releases without mutation"
```

---

### Task 6: Implement ACTIVATE, two-hit health verification, and first-takeover rollback

**Files:**
- Modify: `agent/digitalafarin_agent/health.py`
- Modify: `agent/digitalafarin_agent/takeover.py`
- Modify: `agent/digitalafarin_agent/operations.py`
- Modify: `agent/tests/test_takeover.py`
- Create/modify: `agent/tests/test_health_and_retention.py` (health helper tests)

**Interfaces:**
- Produces `check_http_health_stable(spec, required_successes=2, ...) -> dict`.
- Produces `activate_service_takeover(payload, apps_root=...) -> dict`.
- `final_state` is `succeeded` or `rolled_back`; `takeover_rollback_failed` is an execution error.
- Source fingerprint drift and unsafe `current` are detected before mutation.

- [ ] **Step 1: Write stable health tests**

In `agent/tests/test_health_and_retention.py` import the new helper and add:

```python
from digitalafarin_agent.health import (
    HealthCheckError,
    check_http_health_stable,
)


def test_stable_health_requires_two_consecutive_successes():
    statuses = iter([200, 500, 200, 200])
    sleeps = []

    result = check_http_health_stable(
        {
            "url": "http://127.0.0.1:9751/",
            "expected_status": 200,
            "attempts": 6,
            "timeout_seconds": 1,
            "interval_seconds": 5,
        },
        request=lambda _url, _timeout: next(statuses),
        sleep=lambda seconds: sleeps.append(seconds),
    )

    assert result["attempts"] == 4
    assert result["consecutive_successes"] == 2
    assert 1 in sleeps
```

Add a failure case where all requests fail and expect `HealthCheckError`.

- [ ] **Step 2: Write ACTIVATE drift/current/rollback tests**

Append to `agent/tests/test_takeover.py`.

Fingerprint drift before mutation:

```python
def test_activate_blocks_fingerprint_drift_before_mutation(
    tmp_path,
    monkeypatch,
):
    payload = {
        **prepare_payload(),
        "source_fingerprint": "a" * 64,
        "release_name": "20260920-120000-aaaaaaa",
        "health_check": prepare_payload()["health_check"],
    }
    release = (
        tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
        / "releases" / payload["release_name"]
    )
    (release / "apps" / "web" / ".next").mkdir(parents=True)

    monkeypatch.setattr(
        "digitalafarin_agent.takeover.inspect_service",
        lambda _unit: snapshot(),
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot",
        lambda _snapshot: "b" * 64,
    )

    mutated = []
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.atomic_activate",
        lambda *_args, **_kwargs: mutated.append("current"),
    )

    with pytest.raises(TakeoverExecutionError) as exc:
        activate_service_takeover(
            payload,
            apps_root=tmp_path / "apps",
        )

    assert exc.value.code == "service_configuration_changed"
    assert mutated == []
```

Unsafe pre-existing current:

```python
def test_activate_rejects_current_symlink_outside_managed_releases(
    tmp_path,
    monkeypatch,
):
    payload = {
        **prepare_payload(),
        "source_fingerprint": "a" * 64,
        "release_name": "20260920-120000-aaaaaaa",
        "health_check": prepare_payload()["health_check"],
    }
    root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    release = root / "releases" / payload["release_name"]
    (release / "apps" / "web" / ".next").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir(parents=True, exist_ok=True)
    (root / "current").symlink_to(outside)

    monkeypatch.setattr(
        "digitalafarin_agent.takeover.inspect_service",
        lambda _unit: snapshot(),
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot",
        lambda _snapshot: "a" * 64,
    )

    with pytest.raises(TakeoverExecutionError) as exc:
        activate_service_takeover(
            payload,
            apps_root=tmp_path / "apps",
        )

    assert exc.value.code == "takeover_activation_failed"
    assert (root / "current").resolve() == outside.resolve()
```

First-takeover rollback:
- no prior `current`;
- mock stable health to fail first activation then succeed after rollback;
- assert managed drop-in removed;
- assert `current` absent after rollback;
- assert restart called twice;
- result `final_state == "rolled_back"`.

Also add rollback-failure case and expect `TakeoverExecutionError.code == "takeover_rollback_failed"`.

- [ ] **Step 3: Run and verify RED**

```bash
python -m pytest -q tests/test_takeover.py tests/test_health_and_retention.py
```

- [ ] **Step 4: Add bounded two-consecutive health helper**

In `agent/digitalafarin_agent/health.py`, factor existing validation into a private helper and implement:

```python
def check_http_health_stable(
    spec: dict,
    *,
    required_successes: int = 2,
    request=_request,
    sleep=time.sleep,
) -> dict:
    url, expected, attempts, timeout, interval = _validated(spec)
    if required_successes != 2:
        raise HealthCheckError("invalid consecutive health requirement")

    streak = 0
    for attempt in range(1, attempts + 1):
        try:
            status = request(url, timeout)
        except Exception:
            status = None

        if status == expected:
            streak += 1
            if streak == required_successes:
                return {
                    "attempts": attempt,
                    "status": status,
                    "consecutive_successes": streak,
                }
        else:
            streak = 0

        if attempt < attempts:
            sleep(1 if streak == 1 else interval)

    raise HealthCheckError("health check failed")
```

Keep `check_http_health()` behavior unchanged for existing deployments.

- [ ] **Step 5: Implement ACTIVATE orchestration**

In `agent/digitalafarin_agent/takeover.py`, add `activate_service_takeover(...)`.

Before any mutation:
- validate payload key allowlist;
- derive service root/release/current/root directory;
- require release is a real directory under `<service_root>/releases`;
- require `.next` still exists;
- re-inspect systemd and compare fingerprint;
- inspect existing `current`: absent is valid, symlink into `releases/` is valid, regular file/directory or link outside `releases/` is rejected;
- reserved managed drop-in must still be absent.

Activation order:

```python
previous = atomic_activate(service_root, release)
dropin = write_managed_dropin(
    payload["unit_name"],
    service_root / "current" / payload["root_directory"],
)
daemon_reload()
restart_takeover_unit(payload["unit_name"])
check_http_health_stable(payload["health_check"])
```

On successful health:

```python
return {
    "takeover_id": payload["takeover_id"],
    "final_state": "succeeded",
    "resolved_commit": payload["exact_commit"],
    "release_name": release.name,
    "previous_current_path": str(previous) if previous else None,
    "managed_dropin_path": str(dropin),
    "events": [
        {"state": "activating", "message": ""},
        {"state": "verifying", "message": ""},
        {"state": "succeeded", "message": ""},
    ],
}
```

On health failure:
1. restore previous `current` if present; otherwise unlink the takeover-created `current`;
2. remove only the reserved managed drop-in;
3. `daemon_reload()`;
4. restart exact unit;
5. run `check_http_health_stable()` against the same frozen health spec.

If rollback health passes, remove the failed release and return:

```python
{
    "takeover_id": payload["takeover_id"],
    "final_state": "rolled_back",
    "resolved_commit": payload["exact_commit"],
    "release_name": release.name,
    "previous_current_path": str(previous) if previous else None,
    "managed_dropin_path": str(dropin),
    "events": [
        {"state": "activating", "message": ""},
        {"state": "verifying", "message": ""},
        {
            "state": "rolled_back",
            "message": "New release failed health verification; original service restored.",
        },
    ],
}
```

If rollback health fails, keep release metadata for forensic inspection and raise:

```python
TakeoverExecutionError(
    "takeover_rollback_failed",
    "Controlled takeover rollback did not restore healthy service.",
)
```

- [ ] **Step 6: Dispatch typed ACTIVATE**

In `agent/digitalafarin_agent/operations.py` import `activate_service_takeover` and add:

```python
if kind == "service.takeover.activate":
    try:
        return activate_service_takeover(payload)
    except TakeoverExecutionError as exc:
        raise OperationExecutionError(exc.code, str(exc)) from exc
```

Again, do not add it to generic `SERVICE_ACTIONS`.

- [ ] **Step 7: Run all touched Agent tests under WSL**

```bash
python -m pytest -q \
  tests/test_takeover.py \
  tests/test_takeover_systemd.py \
  tests/test_health_and_retention.py \
  tests/test_operations.py \
  tests/test_release_engine.py \
  tests/test_systemd_executor.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add agent/digitalafarin_agent/health.py agent/digitalafarin_agent/takeover.py agent/digitalafarin_agent/operations.py agent/tests/test_takeover.py agent/tests/test_health_and_retention.py
git commit -m "feat: activate and roll back controlled takeovers"
```

---

### Task 7: Add ACTIVATE/cancel/read API and final takeover result transaction

**Files:**
- Modify: `apps/api/control/services/takeovers.py`
- Modify: `apps/api/control/services/execution.py`
- Modify: `apps/api/control/takeover_views.py`
- Modify: `apps/api/control/control_urls.py`
- Modify: `apps/api/control/tests/test_takeover_api.py`
- Modify: `apps/api/control/tests/test_takeover_results.py`

**Interfaces:**
- Produces `queue_takeover_activation(takeover, requested_by) -> Operation`.
- Produces `cancel_prepared_takeover(takeover, actor) -> ServiceTakeover`.
- Adds `GET /api/control/v1/takeovers/<id>/`.
- Adds `POST /api/control/v1/takeovers/<id>/activate/`.
- Adds `POST /api/control/v1/takeovers/<id>/cancel/`.
- Successful ACTIVATE creates exactly one takeover Release and atomically sets Service to `managed`.

- [ ] **Step 1: Add failing API tests for detail/activate/cancel**

Append to `test_takeover_api.py`:

```python
def test_prepared_takeover_queues_activate_operation_only_once(self):
    created = self.prepare()
    takeover = ServiceTakeover.objects.get(public_id=created.json()["id"])
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

    response = self.client.post(
        f"/api/control/v1/takeovers/{takeover.public_id}/activate/",
        {},
        format="json",
    )

    self.assertEqual(response.status_code, 202)
    takeover.refresh_from_db()
    self.assertEqual(
        takeover.activate_operation.kind,
        Operation.KIND_TAKEOVER_ACTIVATE,
    )
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
    created = self.prepare()
    takeover = ServiceTakeover.objects.get(public_id=created.json()["id"])
    takeover.state = ServiceTakeover.STATE_PREPARED
    takeover.save(update_fields=["state"])

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
```

- [ ] **Step 2: Add failing successful/rollback finalization tests**

Append to `test_takeover_results.py`:
- seed takeover as `prepared`;
- queue ACTIVATE;
- claim/start;
- complete with `final_state="succeeded"`;
- assert:
  - takeover `succeeded`;
  - service `managed`;
  - one `Release` exists with `takeover_id`, `deployment_id is None`;
  - `activated_at` set;
  - repeat `apply_takeover_result(...)` directly and still one Release.

Add `rolled_back` completion and assert:
- state `rolled_back`;
- Service still configured;
- no Release row.

Add failed operation with `error_code="takeover_rollback_failed"` and assert:
- state `rollback_failed`;
- Service configured;
- no Release.

- [ ] **Step 3: Run API result tests and verify RED**

```powershell
cd apps\api
.\.venv\Scripts\python.exe manage.py test control.tests.test_takeover_api control.tests.test_takeover_results -v 2
```

- [ ] **Step 4: Queue activation and cancellation in the domain service**

In `services/takeovers.py`:

```python
@transaction.atomic
def queue_takeover_activation(
    *,
    takeover: ServiceTakeover,
    requested_by: str,
) -> Operation:
    takeover = ServiceTakeover.objects.select_for_update().select_related(
        "service__target_server"
    ).get(pk=takeover.pk)

    if takeover.state != ServiceTakeover.STATE_PREPARED:
        raise TakeoverError(
            "takeover_not_prepared",
            "Takeover must be prepared before activation.",
        )
    if takeover.activate_operation_id:
        raise TakeoverError(
            "takeover_already_active",
            "Takeover activation is already queued.",
        )

    operation = create_operation(
        server=takeover.service.target_server,
        kind=Operation.KIND_TAKEOVER_ACTIVATE,
        payload={"takeover_id": str(takeover.public_id)},
        actor=requested_by,
    )
    takeover.activate_operation = operation
    takeover.save(update_fields=["activate_operation", "updated_at"])

    AuditEvent.objects.create(
        event_type="service.takeover.activation_requested",
        target_type="service_takeover",
        target_id=str(takeover.public_id),
        actor=requested_by,
        metadata={
            "service_id": str(takeover.service.public_id),
            "exact_commit": takeover.requested_commit,
        },
    )
    return operation


@transaction.atomic
def cancel_prepared_takeover(
    *,
    takeover: ServiceTakeover,
    actor: str,
) -> ServiceTakeover:
    takeover = ServiceTakeover.objects.select_for_update().get(pk=takeover.pk)
    if takeover.state != ServiceTakeover.STATE_PREPARED:
        raise TakeoverError(
            "takeover_not_prepared",
            "Only a prepared takeover can be canceled.",
        )
    if takeover.activate_operation_id:
        raise TakeoverError(
            "takeover_already_active",
            "Takeover activation has already been queued.",
        )
    return transition_takeover(
        takeover.public_id,
        ServiceTakeover.STATE_CANCELED,
        actor=actor,
    )
```

- [ ] **Step 5: Add ACTIVATE execution context**

Extend `build_execution_context()`:

```python
if operation.kind == Operation.KIND_TAKEOVER_ACTIVATE:
    takeover = ServiceTakeover.objects.select_related(
        "service__project",
        "service__target_server",
    ).get(
        public_id=operation.payload["takeover_id"],
        service__target_server=operation.server,
    )
    service = takeover.service
    expected_release_path = (
        f"/srv/digitalafarin/apps/{service.project.slug}/"
        f"{service.name}/releases/{takeover.release_name}"
    )
    return {
        "takeover_id": str(takeover.public_id),
        "service_id": str(service.public_id),
        "project_slug": service.project.slug,
        "service_name": service.name,
        "unit_name": service.unit_name,
        "exact_commit": takeover.requested_commit,
        "root_directory": service.root_directory,
        "source_fingerprint": takeover.source_fingerprint,
        "release_name": takeover.release_name,
        "release_path": expected_release_path,
        "health_check": takeover.health_check_snapshot,
    }
```

The persisted free-form `release_path` is not trusted to choose an execution path; the execution path is re-derived from slugs + validated release name.

- [ ] **Step 6: Extend started hook and ACTIVATE result finalization**

`mark_takeover_operation_started`:
- PREPARE queued -> inspecting;
- ACTIVATE prepared -> activating.

In `apply_takeover_result`:
- failed ACTIVATE with `error_code == "takeover_rollback_failed"` -> `rollback_failed`;
- other failed ACTIVATE -> `failed`;
- success result allows only `succeeded` or `rolled_back`;
- transition `activating -> verifying -> succeeded/rolled_back`;
- successful finalization uses one `transaction.atomic()` and one `select_for_update()` for takeover/service;
- validate commit/release name against prepared fields;
- create takeover Release with `get_or_create(takeover=takeover, ...)`;
- set `activated_at=timezone.now()`;
- set `service.lifecycle_state = Service.LIFECYCLE_MANAGED`;
- set `previous_current_path`, `managed_dropin_path`, completion fields;
- write `service.takeover.succeeded` audit metadata without secret values;
- second application of the identical success result returns the already-succeeded takeover and does not create a second Release.

For `rolled_back`, do not create a Release and do not change Service lifecycle.

- [ ] **Step 7: Add detail/activate/cancel views and routes**

Add views:

```python
class TakeoverDetailView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:read")]

    def get(self, request, takeover_id):
        try:
            takeover = ServiceTakeover.objects.select_related(
                "service", "prepare_operation", "activate_operation"
            ).get(public_id=takeover_id)
        except ServiceTakeover.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(ServiceTakeoverSerializer(takeover).data)
```

`TakeoverActivateView` and `TakeoverCancelView` use `operations:create`, call the domain methods, and map `TakeoverError` to 409.

Routes:

```python
path(
    "takeovers/<uuid:takeover_id>/",
    takeover_views.TakeoverDetailView.as_view(),
),
path(
    "takeovers/<uuid:takeover_id>/activate/",
    takeover_views.TakeoverActivateView.as_view(),
),
path(
    "takeovers/<uuid:takeover_id>/cancel/",
    takeover_views.TakeoverCancelView.as_view(),
),
```

- [ ] **Step 8: Run takeover + deployment regression tests**

```powershell
.\.venv\Scripts\python.exe manage.py test \
  control.tests.test_takeover_models \
  control.tests.test_takeover_api \
  control.tests.test_takeover_results \
  control.tests.test_deployment_actions \
  -v 2
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add apps/api/control/services/takeovers.py apps/api/control/services/execution.py apps/api/control/takeover_views.py apps/api/control/control_urls.py apps/api/control/tests/test_takeover_api.py apps/api/control/tests/test_takeover_results.py
git commit -m "feat: activate and finalize controlled takeovers"
```

---

### Task 8: Expose strictly typed takeover MCP tools

**Files:**
- Modify: `mcp/digitalafarin_vps_mcp/control_plane.py`
- Modify: `mcp/digitalafarin_vps_mcp/server.py`
- Modify: `mcp/tests/test_control_plane.py`
- Modify: `mcp/tests/test_server.py`
- Modify: `mcp/tests/test_server_contract_static.py`

**Interfaces:**
- `prepare_service_takeover(service_id, commit)`
- `get_service_takeover(takeover_id)`
- `activate_service_takeover(takeover_id)`
- `cancel_service_takeover(takeover_id)`
- MCP tools use only UUIDs and exact SHA; no path/unit/shell fields.

- [ ] **Step 1: Add failing ControlPlaneClient request tests**

In `mcp/tests/test_control_plane.py`, add tests that assert exact method/path/body:

```python
@pytest.mark.asyncio
async def test_prepare_takeover_posts_only_service_and_exact_commit(httpx_mock):
    service_id = "11111111-1111-1111-1111-111111111111"
    commit = "a" * 40
    httpx_mock.add_response(
        method="POST",
        url=f"http://control/api/control/v1/services/{service_id}/takeovers/",
        json={"id": "22222222-2222-2222-2222-222222222222"},
        status_code=201,
    )
    client = ControlPlaneClient("http://control", "token")

    result = await client.prepare_service_takeover(service_id, commit)

    assert result["id"] == "22222222-2222-2222-2222-222222222222"
```

Also test:
- invalid non-UUID service ID rejected locally;
- `commit="main"` rejected locally;
- GET detail route;
- POST activate with `{}`;
- POST cancel with `{}`.

- [ ] **Step 2: Run MCP tests and verify RED**

```powershell
cd mcp
.\.venv\Scripts\python.exe -m pytest -q tests/test_control_plane.py
```

- [ ] **Step 3: Add client methods with exact local validation**

In `control_plane.py` add:

```python
_EXACT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


async def prepare_service_takeover(
    self,
    service_id: str,
    commit: str,
) -> dict:
    _validate_uuid(service_id, "service_id")
    if not _EXACT_COMMIT_RE.fullmatch(commit):
        raise MCPDomainError(
            "invalid_request",
            "commit must be an exact lowercase 40-character Git SHA.",
        )
    return await self._post(
        f"/api/control/v1/services/{service_id}/takeovers/",
        {"commit": commit},
    )


async def get_service_takeover(self, takeover_id: str) -> dict:
    _validate_uuid(takeover_id, "takeover_id")
    return await self._get(
        f"/api/control/v1/takeovers/{takeover_id}/"
    )


async def activate_service_takeover(self, takeover_id: str) -> dict:
    _validate_uuid(takeover_id, "takeover_id")
    return await self._post(
        f"/api/control/v1/takeovers/{takeover_id}/activate/",
        {},
    )


async def cancel_service_takeover(self, takeover_id: str) -> dict:
    _validate_uuid(takeover_id, "takeover_id")
    return await self._post(
        f"/api/control/v1/takeovers/{takeover_id}/cancel/",
        {},
    )
```

Extend `_post` conflict normalization so stable takeover API error codes can be returned as `MCPDomainError.code` rather than collapsing every 409 to `invalid_request`. Allow only the explicit Stage B3 codes from the spec.

- [ ] **Step 4: Add four MCP tools**

In `server.py`:

```python
@mcp.tool()
async def vps_prepare_service_takeover(
    service_id: str,
    commit: str,
) -> dict[str, Any]:
    """Prepare an exact-commit controlled takeover without mutating or restarting the service."""
    return await _safe(
        client.prepare_service_takeover(service_id, commit)
    )


@mcp.tool()
async def vps_get_service_takeover(
    takeover_id: str,
) -> dict[str, Any]:
    """Read one non-secret controlled takeover record."""
    return await _safe(client.get_service_takeover(takeover_id))


@mcp.tool()
async def vps_activate_service_takeover(
    takeover_id: str,
) -> dict[str, Any]:
    """Activate one already-prepared takeover using only server-derived execution metadata."""
    return await _safe(
        client.activate_service_takeover(takeover_id)
    )


@mcp.tool()
async def vps_cancel_service_takeover(
    takeover_id: str,
) -> dict[str, Any]:
    """Cancel one prepared takeover before activation."""
    return await _safe(
        client.cancel_service_takeover(takeover_id)
    )
```

No tool takes `unit_name`, path, command, environment, or systemctl action.

- [ ] **Step 5: Update FakeControlPlane/tool contract tests**

Add matching async methods to the test fake. Assert tool discovery contains all four names and that schemas expose only:
- prepare: `service_id`, `commit`;
- get/activate/cancel: `takeover_id`.

Update `test_server_contract_static.py` expected allowlist and assert forbidden tokens like `shell`, `command`, `filesystem_path`, `unit_name` are absent from takeover tool signatures.

- [ ] **Step 6: Run the full MCP suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all MCP tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add mcp/digitalafarin_vps_mcp/control_plane.py mcp/digitalafarin_vps_mcp/server.py mcp/tests/test_control_plane.py mcp/tests/test_server.py mcp/tests/test_server_contract_static.py
git commit -m "feat: expose typed controlled takeover tools"
```

---

### Task 9: Add the Controlled Takeover Web flow

**Files:**
- Create: `apps/web/lib/takeovers.ts`
- Create: `apps/web/lib/takeovers.test.ts`
- Modify: `apps/web/lib/control-plane.ts`
- Create: `apps/web/app/services/takeover-actions.ts`
- Modify: `apps/web/app/services/[serviceId]/page.tsx`

**Interfaces:**
- Pure exact-SHA builder/validator.
- Control Plane methods: `listServiceTakeovers`, `prepareServiceTakeover`, `getTakeover`, `activateTakeover`, `cancelTakeover`.
- Configured service page shows prepare UI.
- Prepared takeover shows snapshot/release summary and explicit activate/cancel actions.
- Managed service hides takeover preparation and keeps existing Deploy UI.

- [ ] **Step 1: Write pure Web tests**

Create `apps/web/lib/takeovers.test.ts`:

```typescript
import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPrepareTakeoverRequest,
  canActivateTakeover,
  canPrepareTakeover,
  takeoverStateLabel,
} from "./takeovers.ts";

test("prepare builder accepts only an exact lowercase commit", () => {
  assert.deepEqual(
    buildPrepareTakeoverRequest("a".repeat(40)),
    { commit: "a".repeat(40) },
  );
  assert.throws(() => buildPrepareTakeoverRequest("main"));
  assert.throws(() => buildPrepareTakeoverRequest("A".repeat(40)));
});

test("only configured services can prepare controlled takeover", () => {
  assert.equal(canPrepareTakeover("adopted"), false);
  assert.equal(canPrepareTakeover("configured"), true);
  assert.equal(canPrepareTakeover("managed"), false);
});

test("only prepared takeover can activate", () => {
  assert.equal(canActivateTakeover("prepared"), true);
  assert.equal(canActivateTakeover("queued"), false);
  assert.equal(canActivateTakeover("succeeded"), false);
});

test("takeover state labels are explicit", () => {
  assert.equal(takeoverStateLabel("prepared"), "Prepared · No cutover yet");
  assert.equal(takeoverStateLabel("succeeded"), "Succeeded · Managed");
  assert.equal(takeoverStateLabel("rolled_back"), "Rolled back · Unmanaged");
  assert.equal(takeoverStateLabel("rollback_failed"), "Rollback failed · Intervention required");
});
```

- [ ] **Step 2: Run Web tests and verify RED**

```powershell
cd apps\web
npm test
```

- [ ] **Step 3: Implement pure helpers**

Create `apps/web/lib/takeovers.ts`:

```typescript
import type { ServiceLifecycle } from "./service-adoption.ts";

export type TakeoverState =
  | "queued"
  | "inspecting"
  | "preparing"
  | "prepared"
  | "activating"
  | "verifying"
  | "succeeded"
  | "failed"
  | "rolled_back"
  | "rollback_failed"
  | "canceled";

const EXACT_COMMIT = /^[0-9a-f]{40}$/;

export function buildPrepareTakeoverRequest(commit: string) {
  const normalized = commit.trim();
  if (!EXACT_COMMIT.test(normalized)) {
    throw new Error("Exact lowercase 40-character commit is required.");
  }
  return { commit: normalized };
}

export function canPrepareTakeover(lifecycle: ServiceLifecycle) {
  return lifecycle === "configured";
}

export function canActivateTakeover(state: TakeoverState) {
  return state === "prepared";
}

export function takeoverStateLabel(state: TakeoverState) {
  const labels: Record<TakeoverState, string> = {
    queued: "Queued",
    inspecting: "Inspecting",
    preparing: "Preparing release",
    prepared: "Prepared · No cutover yet",
    activating: "Activating",
    verifying: "Verifying health",
    succeeded: "Succeeded · Managed",
    failed: "Failed · Unmanaged",
    rolled_back: "Rolled back · Unmanaged",
    rollback_failed: "Rollback failed · Intervention required",
    canceled: "Canceled",
  };
  return labels[state];
}
```

- [ ] **Step 4: Add Takeover/Operation types and client methods**

In `control-plane.ts` extend `Operation.kind` with:

```typescript
| "service.takeover.prepare"
| "service.takeover.activate"
```

Add:

```typescript
export type ServiceTakeover = {
  id: string;
  service_id: string;
  state: TakeoverState;
  requested_commit: string;
  resolved_commit: string;
  source_fingerprint: string;
  source_snapshot: Record<string, unknown>;
  release_name: string;
  release_path: string;
  previous_current_path: string | null;
  managed_dropin_path: string;
  health_check_snapshot: Record<string, unknown>;
  prepare_operation_id: string | null;
  activate_operation_id: string | null;
  failure_code: string;
  failure_message: string;
  queued_at: string;
  prepared_at: string | null;
  started_at: string | null;
  completed_at: string | null;
};
```

Import `TakeoverState`/builder and add:

```typescript
export async function listServiceTakeovers(
  serviceId: string,
): Promise<ServiceTakeover[]> {
  const result = await request<{ items: ServiceTakeover[] }>(
    `/api/control/v1/services/${encodeURIComponent(serviceId)}/takeovers/`,
  );
  return result.items;
}

export function prepareServiceTakeover(
  serviceId: string,
  commit: string,
): Promise<ServiceTakeover> {
  return request(
    `/api/control/v1/services/${encodeURIComponent(serviceId)}/takeovers/`,
    {
      method: "POST",
      body: JSON.stringify(buildPrepareTakeoverRequest(commit)),
    },
  );
}

export function getTakeover(
  takeoverId: string,
): Promise<ServiceTakeover> {
  return request(
    `/api/control/v1/takeovers/${encodeURIComponent(takeoverId)}/`,
  );
}

export function activateTakeover(
  takeoverId: string,
): Promise<ServiceTakeover> {
  return request(
    `/api/control/v1/takeovers/${encodeURIComponent(takeoverId)}/activate/`,
    { method: "POST", body: "{}" },
  );
}

export function cancelTakeover(
  takeoverId: string,
): Promise<ServiceTakeover> {
  return request(
    `/api/control/v1/takeovers/${encodeURIComponent(takeoverId)}/cancel/`,
    { method: "POST", body: "{}" },
  );
}
```

- [ ] **Step 5: Add server actions**

Create `apps/web/app/services/takeover-actions.ts`:

```typescript
"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import {
  activateTakeover,
  cancelTakeover,
  prepareServiceTakeover,
} from "@/lib/control-plane";

export async function prepareTakeoverAction(formData: FormData) {
  const serviceId = String(formData.get("service_id") ?? "");
  const commit = String(formData.get("commit") ?? "").trim();
  await prepareServiceTakeover(serviceId, commit);
  revalidatePath(`/services/${serviceId}`);
  redirect(`/services/${serviceId}`);
}

export async function activateTakeoverAction(formData: FormData) {
  const serviceId = String(formData.get("service_id") ?? "");
  const takeoverId = String(formData.get("takeover_id") ?? "");
  await activateTakeover(takeoverId);
  revalidatePath(`/services/${serviceId}`);
  redirect(`/services/${serviceId}`);
}

export async function cancelTakeoverAction(formData: FormData) {
  const serviceId = String(formData.get("service_id") ?? "");
  const takeoverId = String(formData.get("takeover_id") ?? "");
  await cancelTakeover(takeoverId);
  revalidatePath(`/services/${serviceId}`);
  redirect(`/services/${serviceId}`);
}
```

- [ ] **Step 6: Render configured/prepared takeover UI**

In `services/[serviceId]/page.tsx`:
- fetch `listServiceTakeovers(service.id)` alongside deployments;
- select the newest active/prepared takeover;
- keep the existing deployment metadata form for `adopted`;
- for `configured`, render a `Controlled takeover` panel.

Prepare form:

```tsx
<form action={prepareTakeoverAction} className="filterBar">
  <input type="hidden" name="service_id" value={service.id} />
  <label>
    <span>Exact production commit</span>
    <input
      name="commit"
      pattern="[0-9a-f]{40}"
      minLength={40}
      maxLength={40}
      required
      placeholder="40-character lowercase Git SHA"
    />
  </label>
  <button type="submit">Prepare controlled takeover</button>
</form>
```

For `prepared`, display:
- requested/resolved commit;
- source fingerprint;
- release name;
- source `working_directory` from `source_snapshot`;
- proposed `/srv/digitalafarin/apps/<project>/<service>/current/<root>`;
- health URL from `health_check_snapshot`;
- explicit Activate and Cancel forms.

Do not render the normal Deploy form until `service.lifecycle_state === "managed"`.

For running Operation states, display Operation-level status if `prepare_operation_id` or `activate_operation_id` exists; do not invent streaming phase progress.

- [ ] **Step 7: Run Web tests, lint, and production build**

```powershell
npm test
npm run lint
npm run build
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```powershell
git add apps/web/lib/takeovers.ts apps/web/lib/takeovers.test.ts apps/web/lib/control-plane.ts apps/web/app/services/takeover-actions.ts "apps/web/app/services/[serviceId]/page.tsx"
git commit -m "feat: add controlled takeover admin flow"
```

---

### Task 10: Document rollout and run the full Stage B3 verification matrix

**Files:**
- Modify: `docs/migration-runbook.md`
- Verify all changed API/Agent/MCP/Web files from Tasks 1–9.

**Interfaces:**
- Produces an operator-safe deploy-before-takeover runbook.
- Proves the final branch passes all test/build gates on the exact tree that will be merged.
- Does not perform the production takeover as part of local implementation.

- [ ] **Step 1: Add Stage B3 runbook section**

Append a `Stage B3 — Controlled Takeover` section containing this operational order:

```text
A. Deploy Stage B3 control-plane code first
   1. fetch exact main commit
   2. build Web as deploy user
   3. apply 0015 migration
   4. install MCP/Agent packages
   5. restart Platform API/MCP/Web/Agent only as required
   6. verify all Platform services healthy

B. PREPARE platform-web
   1. use exact Stage B3 production SHA, never the old Stage B2 SHA
   2. verify takeover becomes prepared
   3. verify source snapshot/fingerprint persisted
   4. verify release exists under /srv
   5. verify systemd WorkingDirectory remains /opt/.../apps/web
   6. verify no managed drop-in exists
   7. verify platform-web MainPID/start time did not change

C. ACTIVATE platform-web
   1. activate prepared takeover
   2. observe typed Operation
   3. verify lifecycle becomes managed only after success
   4. verify WorkingDirectory is /srv/.../current/apps/web
   5. verify User=deploy, Group=www-data
   6. verify EnvironmentFile remains /etc/digitalafarin-platform/web.env
   7. verify ExecStart remains npm start on 127.0.0.1:9751
   8. verify loopback health
   9. verify generic protected restart remains blocked
   10. verify Oily/KhoshVisa services were not mutated

D. Failure acceptance
   If activation health fails and rollback succeeds:
   - Service remains configured
   - managed drop-in is absent
   - first-takeover current link is restored to its previous state
   - original /opt-based Web is healthy
   - no Release row is marked active

E. rollback_failed
   - Service remains configured
   - stop all automated deployment/takeover actions for that service
   - inspect takeover/operation/audit plus systemd journal manually
```

Include the production path learned during Stage B2:

```text
Repo: /opt/digitalafarin-platform
API: 127.0.0.1:9750
Web: 127.0.0.1:9751
MCP: 127.0.0.1:3060
Web env: /etc/digitalafarin-platform/web.env
```

State explicitly that Oily is not a Stage B3 first-candidate.

- [ ] **Step 2: Run final Django verification on the final tree**

From PowerShell:

```powershell
cd "D:\projects\next-drf projects\digitalafarin-platform\apps\api"

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test control.tests -v 2
.\.venv\Scripts\python.exe manage.py check
```

Expected:
- `No changes detected`;
- all control tests PASS;
- `System check identified no issues`.

- [ ] **Step 3: Run the full Agent suite on Ubuntu/WSL**

Use Ubuntu directly to avoid Windows symlink/mode false negatives:

```bash
cd "/mnt/d/projects/next-drf projects/digitalafarin-platform/agent"

rm -rf /tmp/da-agent-b3-final
python3 -m venv /tmp/da-agent-b3-final
source /tmp/da-agent-b3-final/bin/activate

python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest -q
```

Expected: full Agent suite PASS on Linux.

- [ ] **Step 4: Run full MCP verification**

From PowerShell:

```powershell
cd "D:\projects\next-drf projects\digitalafarin-platform\mcp"

.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all MCP tests PASS.

- [ ] **Step 5: Run full Web verification**

```powershell
cd "D:\projects\next-drf projects\digitalafarin-platform\apps\web"

npm ci
npm test
npm run lint
npm run build
```

Expected:
- Node tests PASS;
- ESLint exits 0;
- Next production TypeScript build succeeds.

- [ ] **Step 6: Run repository integrity checks**

```powershell
cd "D:\projects\next-drf projects\digitalafarin-platform"

git diff --check
git status --short
git log --oneline --decorate -15
```

Expected:
- `git diff --check` has no output;
- no accidental `PROMPT.md` staging;
- only intentional Stage B3 changes are present before the final commit/review.

- [ ] **Step 7: Commit runbook/final documentation**

```powershell
git add docs/migration-runbook.md
git commit -m "docs: add Stage B3 takeover runbook"
```

- [ ] **Step 8: Final whole-branch review checklist**

Before merge, inspect the branch diff and confirm all are true:

```text
[ ] no code weakens SystemdExecutor protected-unit rejection
[ ] PREPARE contains no daemon-reload/restart/current/drop-in mutation
[ ] ACTIVATE rechecks fingerprint before mutation
[ ] takeover Operation payload contains only takeover_id
[ ] exact commit validation exists in API, MCP, and Agent
[ ] source build user is rejected when root/missing
[ ] base unit is never written
[ ] drop-in path is derived, fixed, atomic, root:root 0644
[ ] current symlink outside managed releases is rejected
[ ] health requires two consecutive successes
[ ] first-takeover rollback removes drop-in and restores prior current state
[ ] rollback_failed never marks Service managed
[ ] successful finalization is idempotent and creates one Release
[ ] Release provenance constraint is Deployment XOR Takeover
[ ] Web Deploy controls remain managed-only
[ ] Oily is absent from first production takeover actions
```

No merge or production rollout occurs until this checklist and the full test matrix are green.
