# Existing Service Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Stage B2 safe adoption of existing systemd services into Projects, allow validated deployment metadata to be stored without takeover, and guarantee that adopted/configured services cannot deploy, restart, or roll back through the deployment surface.

**Architecture:** Extend the existing `Service` model with a persisted real `unit_name` and lifecycle state (`adopted`, `configured`, `managed`). Keep `ServiceSnapshot` as ephemeral inventory, derive live inventory/protected status at read time, and add narrow metadata-only adoption/configuration endpoints plus matching MCP/Web flows. Existing managed services are backfilled to `managed` with their current computed unit names, while all deployment entry points enforce `managed` in the domain layer and execution context uses persisted `service.unit_name`.

**Tech Stack:** Django 5.2 + DRF, PostgreSQL/SQLite test DB, Python MCP SDK + httpx, Next.js 16 + TypeScript, Node built-in test runner, systemd inventory already reported by the Host Agent.

**Spec:** `docs/superpowers/specs/2026-09-16-existing-service-adoption-design.md`

## Global Constraints

- Stage B2 is metadata-only adoption/configuration; no controlled takeover is implemented.
- No Stage B2 path may rewrite/install systemd units, change `ExecStart`/`WorkingDirectory`/env/user/group, or migrate workload files.
- Adoption and deployment configuration must create **zero** `Operation` rows.
- `configured -> managed` does not exist in Stage B2.
- Deployment, redeploy, and rollback require `Service.lifecycle_state == "managed"` in the domain layer.
- Existing managed Service rows must remain deployment-compatible after migration.
- Existing managed unit names are backfilled as `<project-slug>-<service-name>.service`.
- A `(target_server, unit_name)` binding is unique.
- `ServiceSnapshot` remains ephemeral inventory and is not referenced by foreign key from `Service`.
- Protected-unit policy remains independent from lifecycle state and must not be weakened.
- The Agent gains no new operation kind or capability in Stage B2.
- MCP tools remain typed and narrow; no arbitrary shell/command/systemd-config surface is added.
- First production acceptance adopts a protected DigitalAfarin Platform unit metadata-only; Oily takeover is out of scope.

---

## File Map

**Django model/migration**
- Modify `apps/api/control/models.py` — Service lifecycle constants, real unit binding, nullable deployment metadata.
- Create `apps/api/control/migrations/0014_service_adoption.py` — additive schema changes, duplicate-binding preflight, backfill, final constraint.
- Create `apps/api/control/tests/test_service_adoption_migration.py` — migration backfill and duplicate-preflight verification.
- Update direct `Service.objects.create` fixtures in existing API tests to provide `unit_name` where required.

**Django adoption/configuration/read API**
- Modify `apps/api/control/deployment_serializers.py` — shared deployment validation, lifecycle/inventory representation, adopt/configure serializers.
- Create `apps/api/control/services/service_adoption.py` — transactional metadata-only adoption/configuration domain functions and stable domain errors.
- Modify `apps/api/control/deployment_views.py` — adopt/configure views and stable error mapping.
- Modify `apps/api/control/control_urls.py` — two Stage B2 routes.
- Modify `apps/api/control/tests/test_project_service_api.py` — adoption/configuration/inventory/protected/no-operation coverage.

**Deployment safety**
- Modify `apps/api/control/services/deployments.py` — managed-only domain gate for deploy/redeploy/rollback.
- Modify `apps/api/control/services/execution.py` — use persisted `service.unit_name`.
- Modify `apps/api/control/deployment_views.py` — expose stable `service_not_managed` conflict code.
- Modify `apps/api/control/tests/test_deployment_actions.py` — block adopted/configured deploy/redeploy/rollback and verify explicit unit execution context.
- Modify `apps/api/control/tests/test_github_webhook.py` — webhook remains blocked for non-managed service.

**MCP**
- Modify `mcp/digitalafarin_vps_mcp/control_plane.py` — typed `adopt_service` and `configure_service_deployment` client methods.
- Modify `mcp/digitalafarin_vps_mcp/server.py` — expose two new tools only.
- Modify `mcp/tests/test_control_plane.py` — exact request mapping and local validation.
- Modify `mcp/tests/test_server.py` — FakeControlPlane + tool discovery/call coverage.
- Modify `mcp/tests/test_server_contract_static.py` — expected tool contract remains allowlisted.

**Web**
- Create `apps/web/lib/service-adoption.ts` — pure request builders and lifecycle presentation helpers.
- Create `apps/web/lib/service-adoption.test.ts` — pure Node tests for narrow payloads and lifecycle labels.
- Modify `apps/web/lib/control-plane.ts` — Stage B2 service types and API client methods.
- Create `apps/web/app/services/adoption-actions.ts` — metadata-only server actions.
- Modify `apps/web/app/projects/[projectId]/page.tsx` — inventory selection/adopt form + lifecycle/status list.
- Modify `apps/web/app/services/[serviceId]/page.tsx` — configure form for adopted/configured, deploy UI only for managed.

**Runbook**
- Modify `docs/migration-runbook.md` — Stage B2 rollout, retry-based Web readiness, acceptance checks, and no-workload-restart rule.

---

### Task 1: Add the Service lifecycle schema and safe data migration

**Files:**
- Modify: `apps/api/control/models.py:225-265`
- Create: `apps/api/control/migrations/0014_service_adoption.py`
- Create: `apps/api/control/tests/test_service_adoption_migration.py`
- Modify fixtures in:
  - `apps/api/control/tests/test_deployment_actions.py`
  - `apps/api/control/tests/test_github_webhook.py`
  - `apps/api/control/tests/test_volumes.py`
  - `apps/api/control/tests/test_domains.py`
  - `apps/api/control/tests/test_deployment_state.py`
  - `apps/api/control/tests/test_database_resources.py`
  - `apps/api/control/tests/test_project_service_api.py`
  - `apps/api/control/tests/test_environment_variables.py`

**Interfaces:**
- Produces `Service.LIFECYCLE_ADOPTED`, `Service.LIFECYCLE_CONFIGURED`, `Service.LIFECYCLE_MANAGED`.
- Produces persisted `Service.unit_name: str` and `Service.lifecycle_state: str`.
- Existing managed rows emerge from migration with `lifecycle_state="managed"` and the old computed unit name.
- Deployment metadata fields accept `NULL` at the database layer only; API contracts remain strict in later tasks.

- [ ] **Step 1: Write migration/model tests before changing the model**

Create `apps/api/control/tests/test_service_adoption_migration.py` with a migration executor test that starts at `0013_domains`, creates one legacy Service, migrates to `0014_service_adoption`, and verifies the backfill:

```python
import importlib
from types import SimpleNamespace

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, SimpleTestCase


class ServiceAdoptionMigrationTests(TransactionTestCase):
    migrate_from = [("control", "0013_domains")]
    migrate_to = [("control", "0014_service_adoption")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Server = old_apps.get_model("control", "Server")
        Project = old_apps.get_model("control", "Project")
        Service = old_apps.get_model("control", "Service")
        server = Server.objects.create(name="Target")
        project = Project.objects.create(name="Oily", slug="oily")
        self.service_pk = Service.objects.create(
            project=project,
            name="web",
            executor="systemd",
            repository="https://github.com/example/oily.git",
            branch="main",
            root_directory=".",
            runtime="node-nextjs",
            install_configuration={},
            build_configuration={},
            service_port=3000,
            target_server=server,
        ).pk
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def test_existing_service_is_backfilled_as_managed_with_old_unit_name(self):
        Service = self.apps.get_model("control", "Service")
        service = Service.objects.get(pk=self.service_pk)
        self.assertEqual(service.lifecycle_state, "managed")
        self.assertEqual(service.unit_name, "oily-web.service")
        self.assertEqual(service.repository, "https://github.com/example/oily.git")
        self.assertEqual(service.runtime, "node-nextjs")
        self.assertEqual(service.service_port, 3000)


class ServiceAdoptionMigrationPreflightTests(SimpleTestCase):
    def test_duplicate_preflight_rejects_same_server_unit_binding(self):
        migration = importlib.import_module("control.migrations.0014_service_adoption")
        rows = [
            SimpleNamespace(target_server_id=1, project=SimpleNamespace(slug="oily"), name="web"),
            SimpleNamespace(target_server_id=1, project=SimpleNamespace(slug="oily"), name="web"),
        ]
        with self.assertRaisesMessage(RuntimeError, "duplicate service unit binding"):
            migration._assert_unique_bindings(rows)
```

- [ ] **Step 2: Run the new migration tests and confirm RED**

Run:

```bash
cd apps/api
.venv/bin/python manage.py test control.tests.test_service_adoption_migration -v 2
```

Expected: FAIL because `0014_service_adoption` and the new model fields do not exist.

- [ ] **Step 3: Modify `Service` with lifecycle constants, real unit binding, and nullable deployment metadata**

Replace the deployment-specific Service field block with:

```python
class Service(models.Model):
    EXECUTOR_SYSTEMD = "systemd"
    RUNTIME_NODE = "node-nextjs"
    RUNTIME_DJANGO = "python-django"

    LIFECYCLE_ADOPTED = "adopted"
    LIFECYCLE_CONFIGURED = "configured"
    LIFECYCLE_MANAGED = "managed"
    LIFECYCLE_CHOICES = [
        (LIFECYCLE_ADOPTED, "Adopted"),
        (LIFECYCLE_CONFIGURED, "Configured"),
        (LIFECYCLE_MANAGED, "Managed"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey(Project, related_name="services", on_delete=models.CASCADE)
    name = models.SlugField(max_length=80)
    executor = models.CharField(
        max_length=20,
        choices=[(EXECUTOR_SYSTEMD, "Systemd")],
        default=EXECUTOR_SYSTEMD,
    )
    unit_name = models.CharField(max_length=255)
    lifecycle_state = models.CharField(
        max_length=16,
        choices=LIFECYCLE_CHOICES,
        default=LIFECYCLE_MANAGED,
    )
    repository = models.URLField(max_length=500, null=True, blank=True)
    branch = models.CharField(max_length=255, null=True, blank=True)
    root_directory = models.CharField(max_length=255, null=True, blank=True)
    runtime = models.CharField(
        max_length=32,
        choices=[(RUNTIME_NODE, "Node/Next.js"), (RUNTIME_DJANGO, "Python/Django")],
        null=True,
        blank=True,
    )
    install_configuration = models.JSONField(default=dict, blank=True)
    build_configuration = models.JSONField(default=dict, blank=True)
    service_port = models.PositiveIntegerField(null=True, blank=True)
    target_server = models.ForeignKey(
        Server, related_name="managed_services", on_delete=models.PROTECT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="uniq_project_service"
            ),
            models.UniqueConstraint(
                fields=["target_server", "unit_name"], name="uniq_server_service_unit"
            ),
        ]
```

- [ ] **Step 4: Create migration `0014_service_adoption.py` with duplicate preflight before the final unique constraint**

Use this migration structure:

```python
from django.db import migrations, models


def _binding(row):
    return row.target_server_id, f"{row.project.slug}-{row.name}.service"


def _assert_unique_bindings(rows):
    seen = set()
    for row in rows:
        key = _binding(row)
        if key in seen:
            raise RuntimeError("duplicate service unit binding")
        seen.add(key)


def backfill_existing_services(apps, schema_editor):
    Service = apps.get_model("control", "Service")
    rows = list(Service.objects.select_related("project").order_by("pk"))
    _assert_unique_bindings(rows)
    for row in rows:
        Service.objects.filter(pk=row.pk).update(
            unit_name=f"{row.project.slug}-{row.name}.service",
            lifecycle_state="managed",
        )


class Migration(migrations.Migration):
    dependencies = [("control", "0013_domains")]

    operations = [
        migrations.AddField(
            model_name="service",
            name="unit_name",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="service",
            name="lifecycle_state",
            field=models.CharField(
                choices=[
                    ("adopted", "Adopted"),
                    ("configured", "Configured"),
                    ("managed", "Managed"),
                ],
                default="managed",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="service",
            name="repository",
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
        migrations.AlterField(
            model_name="service",
            name="branch",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="service",
            name="root_directory",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="service",
            name="runtime",
            field=models.CharField(
                blank=True,
                choices=[("node-nextjs", "Node/Next.js"), ("python-django", "Python/Django")],
                max_length=32,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="service",
            name="service_port",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_existing_services, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="service",
            name="unit_name",
            field=models.CharField(max_length=255),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.UniqueConstraint(
                fields=("target_server", "unit_name"),
                name="uniq_server_service_unit",
            ),
        ),
    ]
```

- [ ] **Step 5: Update direct managed-service test fixtures with explicit old-compatible unit names**

For every existing direct `Service.objects.create` fixture, add the deterministic unit name that the deployment engine previously computed. Example:

```python
self.service = Service.objects.create(
    project=self.project,
    name="web",
    unit_name="oily-web.service",
    lifecycle_state=Service.LIFECYCLE_MANAGED,
    repository="https://github.com/example/oily.git",
    branch="main",
    runtime="node-nextjs",
    service_port=3000,
    target_server=self.server,
)
```

Use each fixture's actual project slug and service name; do not invent a different unit naming convention.

- [ ] **Step 6: Run migration/model regression tests**

Run:

```bash
cd apps/api
.venv/bin/python manage.py test control.tests.test_service_adoption_migration -v 2
.venv/bin/python manage.py test control.tests -v 2
.venv/bin/python manage.py makemigrations --check --dry-run
```

Expected: all tests PASS and `makemigrations --check --dry-run` reports no model changes.

- [ ] **Step 7: Commit the schema slice**

```bash
git add apps/api/control/models.py apps/api/control/migrations/0014_service_adoption.py apps/api/control/tests
git commit -m "feat: add service adoption lifecycle schema"
```

---

### Task 2: Add reusable deployment validation and lifecycle-aware Service representation

**Files:**
- Modify: `apps/api/control/deployment_serializers.py`
- Modify: `apps/api/control/control_serializers.py`
- Modify: `apps/api/control/tests/test_project_service_api.py`
- Modify: `apps/api/control/tests/test_control_api.py`

**Interfaces:**
- Produces `validate_deployment_configuration(attrs: dict) -> dict` for both managed create and Stage B2 configuration.
- Produces `AdoptServiceSerializer` with `server_id`, `unit_name`, `name` only.
- Produces `DeploymentConfigurationSerializer` with the complete deployment metadata contract only.
- `ServiceSerializer` read output gains `unit_name`, `lifecycle_state`, `inventory_status`, live systemd fields, and `protected`.
- `ServiceReadSerializer` inventory output gains `protected`, derived with the existing centralized `is_protected_unit` helper.
- Existing managed create still requires repository/branch/runtime/service_port and auto-persists the old computed `unit_name` with state `managed`.

- [ ] **Step 1: Write serializer/read tests first**

Add tests to `test_project_service_api.py` that verify:

```python
def test_managed_service_create_persists_unit_and_managed_lifecycle(self):
    response = self.client.post(
        f"/api/control/v1/projects/{self.project.public_id}/services/",
        {
            "name": "web",
            "executor": "systemd",
            "repository": "https://github.com/example/oily.git",
            "branch": "main",
            "root_directory": ".",
            "runtime": "node-nextjs",
            "install_configuration": {"package_manager": "npm", "lockfile": "package-lock.json"},
            "build_configuration": {"build_script": "build"},
            "service_port": 3000,
            "target_server_id": str(self.server.public_id),
        },
        format="json",
    )
    self.assertEqual(response.status_code, 201)
    body = response.json()
    self.assertEqual(body["unit_name"], "oily-web.service")
    self.assertEqual(body["lifecycle_state"], "managed")


def test_service_representation_marks_missing_inventory_without_deleting_service(self):
    service = Service.objects.create(
        project=self.project,
        name="backend",
        unit_name="oily-backend.service",
        lifecycle_state=Service.LIFECYCLE_ADOPTED,
        target_server=self.server,
    )
    response = self.client.get(f"/api/control/v1/projects/{self.project.public_id}/")
    item = next(row for row in response.json()["services"] if row["id"] == str(service.public_id))
    self.assertEqual(item["inventory_status"], "missing")
    self.assertIsNone(item["active_state"])
    self.assertTrue(Service.objects.filter(pk=service.pk).exists())
```

Also add a protected representation test with a snapshot named `digitalafarin-platform-web.service` and assert `protected is True`.

Add to `test_control_api.py`:

```python
def test_inventory_service_exposes_centralized_protected_policy(self):
    response = self.client.get("/api/control/v1/servers/default/services/")
    item = response.json()["items"][0]
    self.assertEqual(item["unit_name"], "digitalafarin-platform-api.service")
    self.assertTrue(item["protected"])
```

- [ ] **Step 2: Run the focused tests and confirm RED**

```bash
cd apps/api
.venv/bin/python manage.py test control.tests.test_project_service_api control.tests.test_control_api -v 2
```

Expected: FAIL because lifecycle/inventory/protected fields are not represented yet and managed create does not persist `unit_name`.

- [ ] **Step 3: Extract shared deployment-configuration validation**

In `deployment_serializers.py`, add:

```python
def validate_deployment_configuration(attrs):
    runtime = attrs["runtime"]
    install = attrs["install_configuration"]
    build = attrs["build_configuration"]
    if set(install) - INSTALL_KEYS[runtime]:
        raise serializers.ValidationError(
            {"install_configuration": "Unsupported install configuration field."}
        )
    if set(build) - BUILD_KEYS[runtime]:
        raise serializers.ValidationError(
            {"build_configuration": "Unsupported build configuration field."}
        )
    return attrs
```

Change `ServiceSerializer.validate()` to call this helper after resolving `target_server`.

- [ ] **Step 4: Add the narrow Stage B2 serializers**

Import `UNIT_PATTERN` and add:

```python
class AdoptServiceSerializer(StrictSerializer):
    server_id = serializers.UUIDField()
    unit_name = serializers.RegexField(UNIT_PATTERN.pattern, max_length=255)
    name = serializers.SlugField(max_length=80)


class DeploymentConfigurationSerializer(StrictSerializer):
    repository = serializers.URLField(max_length=500)
    branch = serializers.RegexField(SAFE_REF.pattern, max_length=255)
    root_directory = serializers.RegexField(SAFE_PATH.pattern, max_length=255, default=".")
    runtime = serializers.ChoiceField(choices=[Service.RUNTIME_NODE, Service.RUNTIME_DJANGO])
    install_configuration = serializers.DictField(default=dict)
    build_configuration = serializers.DictField(default=dict)
    service_port = serializers.IntegerField(min_value=1, max_value=65535)

    def validate(self, attrs):
        return validate_deployment_configuration(attrs)
```

- [ ] **Step 5: Make managed create persist the explicit old-compatible unit and managed lifecycle**

Update `ServiceSerializer.create()` to:

```python
def create(self, validated_data):
    project = self.context["project"]
    name = validated_data["name"]
    return Service.objects.create(
        project=project,
        unit_name=f"{project.slug}-{name}.service",
        lifecycle_state=Service.LIFECYCLE_MANAGED,
        **validated_data,
    )
```

Add read-only fields:

```python
unit_name = serializers.CharField(read_only=True)
lifecycle_state = serializers.ChoiceField(choices=Service.LIFECYCLE_CHOICES, read_only=True)
```

- [ ] **Step 6: Add inventory/protected fields in `to_representation()`**

Use the existing inventory relation `target_server.services` and existing protected helper:

```python
from control.operation_serializers import StrictSerializer, UNIT_PATTERN, is_protected_unit


def to_representation(self, instance):
    data = super().to_representation(instance)
    data["target_server_id"] = str(instance.target_server.public_id)
    snapshot = instance.target_server.services.filter(unit_name=instance.unit_name).first()
    data["protected"] = is_protected_unit(instance.unit_name)
    if snapshot is None:
        data.update(
            inventory_status="missing",
            load_state=None,
            active_state=None,
            sub_state=None,
            inventory_last_seen_at=None,
        )
    else:
        data.update(
            inventory_status="present",
            load_state=snapshot.load_state,
            active_state=snapshot.active_state,
            sub_state=snapshot.sub_state,
            inventory_last_seen_at=snapshot.last_seen_at,
        )
    return data
```

- [ ] **Step 7: Expose protected policy on raw inventory using the same helper**

In `control_serializers.py`, import `is_protected_unit` and add a method field:

```python
from control.operation_serializers import is_protected_unit


class ServiceReadSerializer(serializers.ModelSerializer):
    protected = serializers.SerializerMethodField()

    def get_protected(self, instance):
        return is_protected_unit(instance.unit_name)

    class Meta:
        model = ServiceSnapshot
        fields = [
            "unit_name",
            "description",
            "load_state",
            "active_state",
            "sub_state",
            "last_seen_at",
            "protected",
        ]
```

- [ ] **Step 8: Run serializer/project tests and full API suite**

```bash
cd apps/api
.venv/bin/python manage.py test control.tests.test_project_service_api control.tests.test_control_api -v 2
.venv/bin/python manage.py test control.tests -v 2
```

Expected: PASS.

- [ ] **Step 9: Commit the representation/validation slice**

```bash
git add apps/api/control/deployment_serializers.py apps/api/control/control_serializers.py apps/api/control/tests/test_project_service_api.py apps/api/control/tests/test_control_api.py
git commit -m "feat: expose service adoption lifecycle metadata"
```

---

### Task 3: Implement metadata-only adoption and deployment-configuration endpoints

**Files:**
- Create: `apps/api/control/services/service_adoption.py`
- Modify: `apps/api/control/deployment_views.py`
- Modify: `apps/api/control/control_urls.py`
- Modify: `apps/api/control/tests/test_project_service_api.py`

**Interfaces:**
- Produces `ServiceAdoptionError(code: str, message: str)`.
- Produces `adopt_existing_service(project, server, unit_name, name, actor) -> Service`.
- Produces `configure_service_deployment(service, configuration, actor) -> Service`.
- Adds `POST /api/control/v1/projects/{project_id}/services/adopt/`.
- Adds `PUT /api/control/v1/services/{service_id}/deployment-configuration/`.
- Neither domain function may create an `Operation`.

- [ ] **Step 1: Write adoption/configuration API tests first**

Add these concrete cases to `test_project_service_api.py`:

```python
def test_adopt_real_inventory_unit_is_metadata_only_and_audited(self):
    ServiceSnapshot.objects.create(
        server=self.server,
        unit_name="oily-backend.service",
        description="Oily backend",
        load_state="loaded",
        active_state="active",
        sub_state="running",
    )
    before_operations = Operation.objects.count()
    response = self.client.post(
        f"/api/control/v1/projects/{self.project.public_id}/services/adopt/",
        {
            "server_id": str(self.server.public_id),
            "unit_name": "oily-backend.service",
            "name": "backend",
        },
        format="json",
    )
    self.assertEqual(response.status_code, 201)
    service = Service.objects.get(public_id=response.json()["id"])
    self.assertEqual(service.lifecycle_state, Service.LIFECYCLE_ADOPTED)
    self.assertEqual(service.unit_name, "oily-backend.service")
    self.assertIsNone(service.repository)
    self.assertEqual(Operation.objects.count(), before_operations)
    self.assertTrue(
        AuditEvent.objects.filter(
            event_type="service.adopted",
            target_id=str(service.public_id),
        ).exists()
    )


def test_adopt_rejects_nonexistent_inventory_duplicate_unit_and_duplicate_project_name(self):
    missing = self.client.post(
        f"/api/control/v1/projects/{self.project.public_id}/services/adopt/",
        {
            "server_id": str(self.server.public_id),
            "unit_name": "missing.service",
            "name": "missing",
        },
        format="json",
    )
    self.assertEqual(missing.status_code, 404)
    self.assertEqual(missing.json()["error"], "inventory_unit_not_found")
```

In the same test, create a real snapshot and an existing Service binding, then assert duplicate unit returns `409 unit_already_adopted`; create another Service with the requested project-local name and assert `409 service_name_in_use`.

Add configuration tests:

```python
def test_configure_adopted_service_moves_to_configured_without_operation(self):
    service = Service.objects.create(
        project=self.project,
        name="backend",
        unit_name="oily-backend.service",
        lifecycle_state=Service.LIFECYCLE_ADOPTED,
        target_server=self.server,
    )
    before_operations = Operation.objects.count()
    response = self.client.put(
        f"/api/control/v1/services/{service.public_id}/deployment-configuration/",
        {
            "repository": "https://github.com/example/oily.git",
            "branch": "main",
            "root_directory": "backend",
            "runtime": "python-django",
            "install_configuration": {"requirements_file": "requirements.txt"},
            "build_configuration": {
                "migrate": True,
                "collectstatic": True,
                "gunicorn_module": "config.wsgi:application",
            },
            "service_port": 8000,
        },
        format="json",
    )
    self.assertEqual(response.status_code, 200)
    service.refresh_from_db()
    self.assertEqual(service.lifecycle_state, Service.LIFECYCLE_CONFIGURED)
    self.assertEqual(service.repository, "https://github.com/example/oily.git")
    self.assertEqual(Operation.objects.count(), before_operations)
```

Also assert partial config returns 400 and managed service configuration returns `409 invalid_service_lifecycle`. Re-run the complete configuration request a second time while the service is already `configured` and assert it remains `configured`. Assert the `service.deployment_configured` audit event contains only identifiers plus the fixed field-name list and does not contain repository credentials, environment values, or command output.

Add a protected-unit adoption test using `digitalafarin-platform-web.service`: adoption itself must return 201, then a generic typed restart request for that unit must still be rejected by the existing protected-unit policy and no restart Operation may be created.

- [ ] **Step 2: Run focused tests and confirm RED**

```bash
cd apps/api
.venv/bin/python manage.py test control.tests.test_project_service_api -v 2
```

Expected: FAIL because both endpoints/domain functions are absent.

- [ ] **Step 3: Create `service_adoption.py` with transactional domain functions**

Use:

```python
from django.db import IntegrityError, transaction

from control.models import AuditEvent, Service, ServiceSnapshot


class ServiceAdoptionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@transaction.atomic
def adopt_existing_service(*, project, server, unit_name: str, name: str, actor: str) -> Service:
    if not ServiceSnapshot.objects.filter(server=server, unit_name=unit_name).exists():
        raise ServiceAdoptionError("inventory_unit_not_found", "Inventory unit was not found.")
    if Service.objects.filter(target_server=server, unit_name=unit_name).exists():
        raise ServiceAdoptionError("unit_already_adopted", "Service unit is already adopted.")
    if Service.objects.filter(project=project, name=name).exists():
        raise ServiceAdoptionError("service_name_in_use", "Project service name is already in use.")
    try:
        service = Service.objects.create(
            project=project,
            name=name,
            executor=Service.EXECUTOR_SYSTEMD,
            unit_name=unit_name,
            lifecycle_state=Service.LIFECYCLE_ADOPTED,
            target_server=server,
        )
    except IntegrityError as exc:
        raise ServiceAdoptionError("adoption_conflict", "Service adoption conflicts with an existing binding.") from exc
    AuditEvent.objects.create(
        event_type="service.adopted",
        target_type="service",
        target_id=str(service.public_id),
        actor=actor,
        metadata={
            "project_id": str(project.public_id),
            "server_id": str(server.public_id),
            "unit_name": unit_name,
            "service_name": name,
        },
    )
    return service


@transaction.atomic
def configure_service_deployment(*, service: Service, configuration: dict, actor: str) -> Service:
    if service.lifecycle_state not in {Service.LIFECYCLE_ADOPTED, Service.LIFECYCLE_CONFIGURED}:
        raise ServiceAdoptionError(
            "invalid_service_lifecycle",
            "Managed services cannot be configured through the Stage B2 endpoint.",
        )
    fields = [
        "repository",
        "branch",
        "root_directory",
        "runtime",
        "install_configuration",
        "build_configuration",
        "service_port",
    ]
    for field in fields:
        setattr(service, field, configuration[field])
    service.lifecycle_state = Service.LIFECYCLE_CONFIGURED
    service.save(update_fields=[*fields, "lifecycle_state", "updated_at"])
    AuditEvent.objects.create(
        event_type="service.deployment_configured",
        target_type="service",
        target_id=str(service.public_id),
        actor=actor,
        metadata={
            "project_id": str(service.project.public_id),
            "server_id": str(service.target_server.public_id),
            "unit_name": service.unit_name,
            "service_name": service.name,
            "fields": fields,
        },
    )
    return service
```

- [ ] **Step 4: Add thin views with stable status/error mapping**

In `deployment_views.py`, import the two serializers/domain functions and add:

```python
class ProjectServiceAdoptView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def post(self, request, project_id):
        try:
            project = Project.objects.get(public_id=project_id)
        except Project.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = AdoptServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            server = Server.objects.get(
                public_id=serializer.validated_data["server_id"],
                is_active=True,
            )
        except Server.DoesNotExist:
            return Response(
                {"error": "server_not_found", "message": "Server not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            service = adopt_existing_service(
                project=project,
                server=server,
                unit_name=serializer.validated_data["unit_name"],
                name=serializer.validated_data["name"],
                actor=request.user.name,
            )
        except ServiceAdoptionError as exc:
            http_status = status.HTTP_404_NOT_FOUND if exc.code == "inventory_unit_not_found" else status.HTTP_409_CONFLICT
            return Response({"error": exc.code, "message": str(exc)}, status=http_status)
        return Response(ServiceSerializer(service).data, status=status.HTTP_201_CREATED)


class ServiceDeploymentConfigurationView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def put(self, request, service_id):
        try:
            service = Service.objects.select_related("project", "target_server").get(public_id=service_id)
        except Service.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = DeploymentConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            service = configure_service_deployment(
                service=service,
                configuration=serializer.validated_data,
                actor=request.user.name,
            )
        except ServiceAdoptionError as exc:
            return Response({"error": exc.code, "message": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(ServiceSerializer(service).data)
```

- [ ] **Step 5: Register the exact Stage B2 routes**

Add to `control_urls.py`:

```python
path(
    "projects/<uuid:project_id>/services/adopt/",
    deployment_views.ProjectServiceAdoptView.as_view(),
),
path(
    "services/<uuid:service_id>/deployment-configuration/",
    deployment_views.ServiceDeploymentConfigurationView.as_view(),
),
```

- [ ] **Step 6: Run focused and full API tests**

```bash
cd apps/api
.venv/bin/python manage.py test control.tests.test_project_service_api -v 2
.venv/bin/python manage.py test control.tests -v 2
```

Expected: PASS and adoption/configuration leave `Operation.objects.count()` unchanged.

- [ ] **Step 7: Commit the Stage B2 API slice**

```bash
git add apps/api/control/deployment_serializers.py apps/api/control/deployment_views.py apps/api/control/control_urls.py apps/api/control/services/service_adoption.py apps/api/control/tests/test_project_service_api.py
git commit -m "feat: add metadata-only service adoption API"
```

---

### Task 4: Enforce managed-only deployment and persist the real unit into execution context

**Files:**
- Modify: `apps/api/control/services/deployments.py`
- Modify: `apps/api/control/services/execution.py`
- Modify: `apps/api/control/deployment_views.py`
- Modify: `apps/api/control/tests/test_deployment_actions.py`
- Modify: `apps/api/control/tests/test_github_webhook.py`

**Interfaces:**
- `DeploymentAdmissionError` gains stable `code`.
- `require_managed_service(service)` is called from both `queue_deployment()` and `queue_rollback()`.
- Blocked lifecycle uses code `service_not_managed` and message `Service has not completed controlled takeover.`
- Agent execution payload uses `service.unit_name` for deploy and rollback.

- [ ] **Step 1: Write the lifecycle safety tests before the gate**

In `test_deployment_actions.py`, add a helper to change the fixture service lifecycle and tests:

```python
def test_adopted_and_configured_services_cannot_deploy(self):
    for state in [Service.LIFECYCLE_ADOPTED, Service.LIFECYCLE_CONFIGURED]:
        self.service.lifecycle_state = state
        self.service.save(update_fields=["lifecycle_state"])
        response = self.client.post(
            f"/api/control/v1/services/{self.service.public_id}/deployments/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "service_not_managed")
        self.assertEqual(Operation.objects.count(), 0)
        self.assertEqual(Deployment.objects.count(), 0)


def test_redeploy_and_rollback_are_blocked_when_source_service_is_not_managed(self):
    source = Deployment.objects.create(
        service=self.service,
        requested_ref="main",
        resolved_commit="b" * 40,
        requested_by="operator",
        state="succeeded",
    )
    release = Release.objects.create(
        service=self.service,
        deployment=source,
        name="release-one",
        exact_commit="b" * 40,
        path="/srv/digitalafarin/apps/oily/web/releases/release-one",
    )
    source.active_release = release
    source.save(update_fields=["active_release"])
    self.service.lifecycle_state = Service.LIFECYCLE_CONFIGURED
    self.service.save(update_fields=["lifecycle_state"])

    redeploy = self.client.post(f"/api/control/v1/deployments/{source.public_id}/redeploy/", {}, format="json")
    rollback = self.client.post(f"/api/control/v1/deployments/{source.public_id}/rollback/", {}, format="json")

    self.assertEqual(redeploy.status_code, 409)
    self.assertEqual(redeploy.json()["error"], "service_not_managed")
    self.assertEqual(rollback.status_code, 409)
    self.assertEqual(rollback.json()["error"], "service_not_managed")
```

Add to the existing execution-context test:

```python
self.service.unit_name = "custom-existing-oily.service"
self.service.save(update_fields=["unit_name"])
```

Then assert:

```python
self.assertEqual(execution["unit_name"], "custom-existing-oily.service")
```

- [ ] **Step 2: Add a GitHub webhook regression for configured services**

In `test_github_webhook.py`, after constructing a valid signed push for the existing fixture, set `self.service.lifecycle_state = Service.LIFECYCLE_CONFIGURED`, save it, send the webhook, and assert HTTP 409 with no Deployment/Operation created.

- [ ] **Step 3: Run the focused tests and confirm RED**

```bash
cd apps/api
.venv/bin/python manage.py test control.tests.test_deployment_actions control.tests.test_github_webhook -v 2
```

Expected: FAIL because lifecycle is not yet enforced and execution still recomputes the unit name.

- [ ] **Step 4: Add stable deployment admission code and managed-only gate**

Change `DeploymentAdmissionError` to:

```python
class DeploymentAdmissionError(RuntimeError):
    def __init__(self, message: str, code: str = "deployment_blocked"):
        super().__init__(message)
        self.code = code
```

Add:

```python
def require_managed_service(service):
    if service.lifecycle_state != service.LIFECYCLE_MANAGED:
        raise DeploymentAdmissionError(
            "Service has not completed controlled takeover.",
            code="service_not_managed",
        )
```

Call `require_managed_service(service)` at the top of `queue_deployment()` before disk admission or creating any row. Call `require_managed_service(source.service)` at the top of `queue_rollback()` before creating any row.

- [ ] **Step 5: Propagate the stable code through deploy/redeploy/rollback views**

Replace hard-coded `deployment_blocked` responses with:

```python
except DeploymentAdmissionError as exc:
    return Response(
        {"error": exc.code, "message": str(exc)},
        status=status.HTTP_409_CONFLICT,
    )
```

Wrap `queue_rollback()` in the same exception mapping; it currently has no `try/except` for admission errors.

- [ ] **Step 6: Use persisted unit name in deploy and rollback execution context**

In `services/execution.py`, replace both computed unit-name expressions with:

```python
"unit_name": service.unit_name,
```

Do not change the release root; Stage B2 does not perform takeover.

- [ ] **Step 7: Run safety regressions and the full API suite**

```bash
cd apps/api
.venv/bin/python manage.py test control.tests.test_deployment_actions control.tests.test_github_webhook -v 2
.venv/bin/python manage.py test control.tests -v 2
```

Expected: PASS. Existing managed deployments stay green; adopted/configured paths return `409 service_not_managed` before creating any Deployment or Operation.

- [ ] **Step 8: Commit the deployment safety slice**

```bash
git add apps/api/control/services/deployments.py apps/api/control/services/execution.py apps/api/control/deployment_views.py apps/api/control/tests/test_deployment_actions.py apps/api/control/tests/test_github_webhook.py
git commit -m "fix: gate deployments by service lifecycle"
```

---

### Task 5: Add narrow MCP adoption/configuration tools

**Files:**
- Modify: `mcp/digitalafarin_vps_mcp/control_plane.py`
- Modify: `mcp/digitalafarin_vps_mcp/server.py`
- Modify: `mcp/tests/test_control_plane.py`
- Modify: `mcp/tests/test_server.py`
- Modify: `mcp/tests/test_server_contract_static.py`

**Interfaces:**
- Produces `ControlPlaneClient.adopt_service(project_id, server_id, unit_name, name)`.
- Produces `ControlPlaneClient.configure_service_deployment(service_id, repository, branch, root_directory, runtime, service_port, install_configuration, build_configuration)`.
- Exposes tools `vps_adopt_service` and `vps_configure_service_deployment`.
- No MCP tool exists for `configured -> managed`.

- [ ] **Step 1: Write exact HTTP mapping tests first**

Add to `mcp/tests/test_control_plane.py`:

```python
@pytest.mark.asyncio
async def test_adopt_service_posts_only_narrow_metadata_payload():
    seen = []

    async def handler(request: httpx.Request):
        seen.append((request.url.path, request.read().decode()))
        return httpx.Response(201, json={"id": "service-id", "lifecycle_state": "adopted"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ControlPlaneClient("http://control", "service-secret", http=http)
    result = await client.adopt_service(
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "oily-backend.service",
        "backend",
    )
    assert result["lifecycle_state"] == "adopted"
    assert seen == [(
        "/api/control/v1/projects/11111111-1111-1111-1111-111111111111/services/adopt/",
        '{"server_id":"22222222-2222-2222-2222-222222222222","unit_name":"oily-backend.service","name":"backend"}',
    )]
    await http.aclose()
```

Add configuration mapping:

```python
@pytest.mark.asyncio
async def test_configure_service_deployment_puts_complete_structured_configuration():
    seen = []

    async def handler(request: httpx.Request):
        seen.append((request.method, request.url.path, request.read().decode()))
        return httpx.Response(200, json={"id": "service-id", "lifecycle_state": "configured"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ControlPlaneClient("http://control", "service-secret", http=http)
    result = await client.configure_service_deployment(
        "33333333-3333-3333-3333-333333333333",
        "https://github.com/example/oily.git",
        "main",
        "backend",
        "python-django",
        8000,
        {"requirements_file": "requirements.txt"},
        {"migrate": True, "collectstatic": True, "gunicorn_module": "config.wsgi:application"},
    )
    assert result["lifecycle_state"] == "configured"
    assert seen[0][0] == "PUT"
    assert seen[0][1] == "/api/control/v1/services/33333333-3333-3333-3333-333333333333/deployment-configuration/"
    assert "command" not in seen[0][2]
    assert "unit_file" not in seen[0][2]
    await http.aclose()
```

- [ ] **Step 2: Run MCP client tests and confirm RED**

```bash
cd mcp
.venv/bin/pytest tests/test_control_plane.py -q
```

Expected: FAIL because the two client methods do not exist.

- [ ] **Step 3: Add local MCP validation and exact methods**

In `control_plane.py`, add these UUID/slug/runtime validation helpers:

```python
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _validate_uuid(value: str, field: str) -> None:
    if not UUID_RE.fullmatch(value):
        raise MCPDomainError("invalid_request", f"{field} must be a UUID.")
```

Add methods:

```python
async def adopt_service(self, project_id: str, server_id: str, unit_name: str, name: str) -> dict:
    _validate_uuid(project_id, "project_id")
    _validate_uuid(server_id, "server_id")
    self._validate_service_name(unit_name)
    if not SLUG_RE.fullmatch(name):
        raise MCPDomainError("invalid_request", "name must be a safe service slug.")
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
```

Add `_put` beside `_post` using the same safe error normalization and headers as `_post`, changing only the HTTP verb:

```python
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
    raise MCPDomainError("control_plane_unavailable", "Control plane request failed.")
```

- [ ] **Step 4: Expose only the two typed MCP tools**

Add to `server.py`:

```python
@mcp.tool()
async def vps_adopt_service(
    project_id: str,
    server_id: str,
    unit_name: str,
    name: str,
) -> dict[str, Any]:
    """Adopt one existing inventory systemd unit as metadata only; no workload operation is queued."""
    return await _safe(client.adopt_service(project_id, server_id, unit_name, name))


@mcp.tool()
async def vps_configure_service_deployment(
    service_id: str,
    repository: str,
    branch: str,
    root_directory: str,
    runtime: Literal["node-nextjs", "python-django"],
    service_port: int,
    install_configuration: dict[str, Any],
    build_configuration: dict[str, Any],
) -> dict[str, Any]:
    """Store validated deployment metadata for an adopted service without enabling management."""
    return await _safe(
        client.configure_service_deployment(
            service_id,
            repository,
            branch,
            root_directory,
            runtime,
            service_port,
            install_configuration,
            build_configuration,
        )
    )
```

- [ ] **Step 5: Update MCP contract tests to exactly 20 tools**

Add FakeControlPlane methods returning `adopted`/`configured`, add call tests for both tools, and extend `EXPECTED` in `test_server_contract_static.py` with:

```python
"vps_adopt_service",
"vps_configure_service_deployment",
```

Keep `BANNED_FRAGMENTS = {"shell", "command", "exec", "terminal", "sql"}` unchanged.

- [ ] **Step 6: Run complete MCP suite**

```bash
cd mcp
.venv/bin/pytest -q
```

Expected: PASS with exactly the allowlisted typed tools; no shell/command tool is introduced.

- [ ] **Step 7: Commit the MCP slice**

```bash
git add mcp/digitalafarin_vps_mcp/control_plane.py mcp/digitalafarin_vps_mcp/server.py mcp/tests
git commit -m "feat: expose typed service adoption MCP tools"
```

---

### Task 6: Add Web request builders and Control Plane client types

**Files:**
- Create: `apps/web/lib/service-adoption.ts`
- Create: `apps/web/lib/service-adoption.test.ts`
- Modify: `apps/web/lib/control-plane.ts`

**Interfaces:**
- Produces `ServiceLifecycle = "adopted" | "configured" | "managed"`.
- Produces pure functions `buildAdoptServiceRequest` and `buildDeploymentConfigurationRequest`.
- Produces `serviceLifecycleLabel` and `serviceCanDeploy`.
- `ManagedService` becomes a lifecycle-aware service type with nullable deployment metadata and live inventory fields.
- Adds `adoptService` and `configureServiceDeployment` API client methods.

- [ ] **Step 1: Write pure Web tests first**

Create `service-adoption.test.ts`:

```typescript
import test from "node:test";
import assert from "node:assert/strict";
import {
  buildAdoptServiceRequest,
  buildDeploymentConfigurationRequest,
  serviceCanDeploy,
  serviceLifecycleLabel,
} from "./service-adoption.ts";

test("adoption builder emits only server unit and project-local name", () => {
  assert.deepEqual(
    buildAdoptServiceRequest("server-id", "oily-backend.service", "backend"),
    { server_id: "server-id", unit_name: "oily-backend.service", name: "backend" },
  );
});

test("configuration builder emits only deployment metadata", () => {
  assert.deepEqual(
    buildDeploymentConfigurationRequest({
      repository: "https://github.com/example/oily.git",
      branch: "main",
      rootDirectory: "backend",
      runtime: "python-django",
      servicePort: 8000,
      installConfiguration: { requirements_file: "requirements.txt" },
      buildConfiguration: { migrate: true, collectstatic: true, gunicorn_module: "config.wsgi:application" },
    }),
    {
      repository: "https://github.com/example/oily.git",
      branch: "main",
      root_directory: "backend",
      runtime: "python-django",
      service_port: 8000,
      install_configuration: { requirements_file: "requirements.txt" },
      build_configuration: { migrate: true, collectstatic: true, gunicorn_module: "config.wsgi:application" },
    },
  );
});

test("only managed services can render deploy controls", () => {
  assert.equal(serviceCanDeploy("adopted"), false);
  assert.equal(serviceCanDeploy("configured"), false);
  assert.equal(serviceCanDeploy("managed"), true);
  assert.equal(serviceLifecycleLabel("adopted"), "Adopted · Unmanaged");
  assert.equal(serviceLifecycleLabel("configured"), "Configured · Unmanaged");
  assert.equal(serviceLifecycleLabel("managed"), "Managed");
});
```

- [ ] **Step 2: Run the new Web test and confirm RED**

```bash
cd apps/web
npm test
```

Expected: FAIL because `service-adoption.ts` does not exist.

- [ ] **Step 3: Create the pure builder/helper module**

Implement `service-adoption.ts` with explicit field validation suitable for server actions:

```typescript
export type ServiceLifecycle = "adopted" | "configured" | "managed";
export type ServiceRuntime = "node-nextjs" | "python-django";

const unitPattern = /^[A-Za-z0-9_.@:-]+\.service$/;
const slugPattern = /^[A-Za-z0-9_-]{1,80}$/;

export function buildAdoptServiceRequest(serverId: string, unitName: string, name: string) {
  if (!serverId || !unitPattern.test(unitName) || !slugPattern.test(name)) {
    throw new Error("Invalid service adoption input");
  }
  return { server_id: serverId, unit_name: unitName, name };
}

export function buildDeploymentConfigurationRequest(input: {
  repository: string;
  branch: string;
  rootDirectory: string;
  runtime: ServiceRuntime;
  servicePort: number;
  installConfiguration: Record<string, unknown>;
  buildConfiguration: Record<string, unknown>;
}) {
  if (!input.repository || !input.branch || !input.rootDirectory || input.servicePort < 1 || input.servicePort > 65535) {
    throw new Error("Invalid deployment configuration input");
  }
  return {
    repository: input.repository,
    branch: input.branch,
    root_directory: input.rootDirectory,
    runtime: input.runtime,
    service_port: input.servicePort,
    install_configuration: input.installConfiguration,
    build_configuration: input.buildConfiguration,
  };
}

export function serviceCanDeploy(state: ServiceLifecycle) {
  return state === "managed";
}

export function serviceLifecycleLabel(state: ServiceLifecycle) {
  return {
    adopted: "Adopted · Unmanaged",
    configured: "Configured · Unmanaged",
    managed: "Managed",
  }[state];
}
```

- [ ] **Step 4: Expand `control-plane.ts` service types without weakening managed semantics**

Replace the current service type with:

```typescript
export type ProjectService = {
  id: string;
  project_id: string;
  name: string;
  executor: "systemd";
  unit_name: string;
  lifecycle_state: ServiceLifecycle;
  repository: string | null;
  branch: string | null;
  root_directory: string | null;
  runtime: ServiceRuntime | null;
  service_port: number | null;
  target_server_id: string;
  inventory_status: "present" | "missing";
  load_state: string | null;
  active_state: string | null;
  sub_state: string | null;
  inventory_last_seen_at: string | null;
  protected: boolean;
};
```

Import `ServiceLifecycle`, `ServiceRuntime`, and the two builders from `./service-adoption`. Change `Project.services` to `ProjectService[]`.

Add:

```typescript
export function adoptService(projectId: string, serverId: string, unitName: string, name: string): Promise<ProjectService> {
  return request(`/api/control/v1/projects/${encodeURIComponent(projectId)}/services/adopt/`, {
    method: "POST",
    body: JSON.stringify(buildAdoptServiceRequest(serverId, unitName, name)),
  });
}

export function configureServiceDeployment(
  serviceId: string,
  input: Parameters<typeof buildDeploymentConfigurationRequest>[0],
): Promise<ProjectService> {
  return request(`/api/control/v1/services/${encodeURIComponent(serviceId)}/deployment-configuration/`, {
    method: "PUT",
    body: JSON.stringify(buildDeploymentConfigurationRequest(input)),
  });
}
```

- [ ] **Step 5: Run Web unit tests**

```bash
cd apps/web
npm test
```

Expected: PASS, including the new narrow-payload tests.

- [ ] **Step 6: Commit the Web data-contract slice**

```bash
git add apps/web/lib/service-adoption.ts apps/web/lib/service-adoption.test.ts apps/web/lib/control-plane.ts
git commit -m "feat: add web service adoption data contracts"
```

---

### Task 7: Add Project adoption UI and lifecycle-safe Service detail UI

**Files:**
- Create: `apps/web/app/services/adoption-actions.ts`
- Modify: `apps/web/app/projects/[projectId]/page.tsx`
- Modify: `apps/web/app/services/[serviceId]/page.tsx`
- Modify: `apps/web/lib/service-adoption.test.ts`

**Interfaces:**
- Project page can select a server using `?server_id=` and render current inventory.
- Adoption action accepts only `project_id`, `server_id`, `unit_name`, `name` from FormData and calls `adoptService`.
- Configuration action parses fixed fields and JSON configuration objects, calls `configureServiceDeployment`, then redirects back to the service.
- Deploy form is rendered only when `serviceCanDeploy(service.lifecycle_state)` is true.

- [ ] **Step 1: Extend pure helper tests for inventory filtering/presentation**

Add a pure helper in `service-adoption.ts`:

```typescript
export function availableInventoryUnits(
  inventory: Array<{ unit_name: string }>,
  boundUnitNames: string[],
) {
  const bound = new Set(boundUnitNames);
  return inventory.filter((item) => !bound.has(item.unit_name));
}
```

Add test:

```typescript
test("already bound inventory units are removed from adoption choices", () => {
  assert.deepEqual(
    availableInventoryUnits(
      [{ unit_name: "a.service" }, { unit_name: "b.service" }],
      ["a.service"],
    ),
    [{ unit_name: "b.service" }],
  );
});
```

Run `npm test` once before implementation to observe RED for the new helper, then add the helper and rerun to GREEN.

- [ ] **Step 2: Create metadata-only server actions**

Create `apps/web/app/services/adoption-actions.ts`:

```typescript
"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { adoptService, configureServiceDeployment } from "@/lib/control-plane";

export async function adoptExistingServiceAction(formData: FormData) {
  const projectId = String(formData.get("project_id") ?? "");
  const serverId = String(formData.get("server_id") ?? "");
  const unitName = String(formData.get("unit_name") ?? "");
  const name = String(formData.get("name") ?? "").trim();
  const service = await adoptService(projectId, serverId, unitName, name);
  revalidatePath(`/projects/${projectId}`);
  redirect(`/services/${service.id}`);
}

export async function configureDeploymentAction(formData: FormData) {
  const serviceId = String(formData.get("service_id") ?? "");
  const runtime = String(formData.get("runtime") ?? "") as "node-nextjs" | "python-django";
  const servicePort = Number(formData.get("service_port"));
  const installConfiguration = JSON.parse(String(formData.get("install_configuration") ?? "{}")) as Record<string, unknown>;
  const buildConfiguration = JSON.parse(String(formData.get("build_configuration") ?? "{}")) as Record<string, unknown>;
  await configureServiceDeployment(serviceId, {
    repository: String(formData.get("repository") ?? "").trim(),
    branch: String(formData.get("branch") ?? "").trim(),
    rootDirectory: String(formData.get("root_directory") ?? ".").trim(),
    runtime,
    servicePort,
    installConfiguration,
    buildConfiguration,
  });
  revalidatePath(`/services/${serviceId}`);
  redirect(`/services/${serviceId}`);
}
```

Keep configuration JSON textareas explicit in Stage B2; do not create a runtime-specific client-state wizard in this stage.

- [ ] **Step 3: Add `Existing services` panel to Project page using server-side query selection**

Change the page signature to accept `searchParams: Promise<{ server_id?: string }>`.

Load:

```typescript
const project = await getProject(projectId);
const servers = await listServers();
const requestedServerId = (await searchParams).server_id;
const selectedServer = servers.find((item) => item.id === requestedServerId) ?? servers.find((item) => item.is_default) ?? servers[0];
const inventory = selectedServer ? await listServices(selectedServer.id) : [];
const available = availableInventoryUnits(inventory, (project.services ?? []).map((item) => item.unit_name));
```

Render a GET form for server selection and a POST form bound to `adoptExistingServiceAction`. The adoption form must contain only hidden `project_id`, hidden `server_id`, one unit `<select name="unit_name">`, one `<input name="name">`, and submit button.

For each inventory option, display the unit name and active/sub state. Append `Protected` when `item.protected` is true; do not duplicate the protected-prefix policy in TypeScript.

- [ ] **Step 4: Make Project service rows lifecycle/inventory aware**

For each Project Service row, render:

```tsx
<p key={service.id}>
  <Link href={`/services/${service.id}`}>{service.name}</Link>
  {" · "}<code>{service.unit_name}</code>
  {" · "}{serviceLifecycleLabel(service.lifecycle_state)}
  {" · "}{service.inventory_status === "missing" ? "missing" : (service.active_state ?? "unknown")}
  {service.protected ? " · Protected" : ""}
</p>
```

- [ ] **Step 5: Make Service detail lifecycle-safe**

On `apps/web/app/services/[serviceId]/page.tsx`, preserve current lookup logic, but render header state/unit/server inventory first.

For `adopted` or `configured`, render a `Configure deployment` form bound to `configureDeploymentAction` with fields:
- repository URL;
- branch;
- root directory;
- runtime select (`node-nextjs`, `python-django`);
- service port;
- install configuration JSON textarea;
- build configuration JSON textarea.

For `configured`, also render the text `Configured · Management disabled` and `Controlled Takeover is handled in Stage B3.`

Wrap the existing Deploy panel in:

```tsx
{serviceCanDeploy(service.lifecycle_state) ? (
  <section className="panel" style={{ marginBottom: 12 }}>
    <div className="panelHeader"><div><h2>Deploy</h2><p>Latest branch or exact commit</p></div></div>
    <form className="filterBar" action={deployAction}>
      <input type="hidden" name="service_id" value={service.id}/>
      <label><span>Exact commit (optional)</span><input name="commit" pattern="[0-9a-f]{40}" /></label>
      <button type="submit">Deploy</button>
    </form>
  </section>
) : null}
```

Keep the deployment-history section visible for all lifecycle states so historical records remain inspectable.

- [ ] **Step 6: Run Web test/lint/build gates**

```bash
cd apps/web
npm test
npm run lint
npm run build
```

Expected: 0 test failures, ESLint exits 0, Next production build exits 0.

- [ ] **Step 7: Commit the Web UI slice**

```bash
git add apps/web/app/services/adoption-actions.ts apps/web/app/projects/'[projectId]'/page.tsx apps/web/app/services/'[serviceId]'/page.tsx apps/web/lib/service-adoption.ts apps/web/lib/service-adoption.test.ts
git commit -m "feat: add safe existing service adoption UI"
```

---

### Task 8: Update rollout runbook and execute the full verification matrix

**Files:**
- Modify: `docs/migration-runbook.md`
- No Agent source changes expected.

**Interfaces:**
- Documents Stage B2 no-downtime production rollout.
- Documents retry-based Web readiness instead of fixed `sleep 5`.
- Documents first acceptance as metadata-only adoption of a protected Platform unit and verifies Operation count does not increase.

- [ ] **Step 1: Update the candidate verification section with the Stage B2 migration test**

Add this API command after the existing full API test:

```bash
.venv/bin/python manage.py test control.tests.test_service_adoption_migration -v 2
```

Keep `manage.py check`, `makemigrations --check --dry-run`, MCP tests, Web tests/lint/build, security greps, and Agent suite unchanged.

- [ ] **Step 2: Replace fixed Web readiness assumptions with bounded retry**

In the production acceptance section, use:

```bash
for attempt in $(seq 1 30); do
  if curl -fsSI http://127.0.0.1:9751/ >/dev/null; then
    echo "Web ready"
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "Web failed readiness window" >&2
    exit 1
  fi
  sleep 1
done
```

This captures the Stage B1 observation that systemd can report active before Next has bound port 9751.

- [ ] **Step 3: Add the Stage B2 production rollout order**

Document this exact order:

```text
1. Confirm production repo is clean and record current SHA.
2. Take/verify the normal database backup/rollback readiness.
3. Pull the reviewed main commit.
4. Install API dependencies and run `manage.py migrate --noinput`.
5. Run `manage.py check`.
6. Install the MCP package update.
7. Build the Web app.
8. Restart only `digitalafarin-platform-api`, `digitalafarin-platform-web`, and `digitalafarin-platform-mcp` as needed to load Stage B2 code.
9. Do not restart adopted workload units and do not restart the Agent solely for Stage B2.
10. Verify existing managed Services remain `managed` with their backfilled unit names.
11. Adopt one protected `digitalafarin-platform-*.service` into the `DigitalAfarin Platform` Project.
12. Compare Operation count before/after adoption and require no increase caused by adoption.
13. Verify the Project/Service UI shows lifecycle, protected state, and live inventory state.
14. Verify deploy on the adopted service returns `service_not_managed` and creates no Deployment/Operation.
15. Optionally configure deployment metadata; verify state becomes `configured` and deploy remains blocked.
16. Only after acceptance, adopt Oily services one at a time; do not perform takeover in Stage B2.
```

- [ ] **Step 4: Run the complete local verification matrix from a clean feature branch**

Run:

```bash
cd apps/api
.venv/bin/python manage.py test control.tests -v 2
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run

cd ../../agent
.venv/bin/pytest -q

cd ../mcp
.venv/bin/pytest -q

cd ../apps/web
npm test
npm run lint
npm run build

cd ../..
PYTHONPATH=.:agent apps/api/.venv/bin/python apps/api/manage.py test acceptance.test_migration_readiness -v 2
git diff --check
git grep -nE 'shell[[:space:]]*=[[:space:]]*True|os\.system' -- apps agent mcp
git grep -nE 'da_(agent|service|enroll)_[A-Za-z0-9]{8,}\.[A-Za-z0-9_-]{40,}' -- ':!*.md'
```

Expected:
- all Python/Node test suites PASS;
- Django check reports no issues;
- migration check reports no pending changes;
- lint/build exit 0;
- both security greps return no matches;
- `git diff --check` returns no output.

- [ ] **Step 5: Verify the final diff contains no Stage B3 takeover implementation**

Run:

```bash
git diff --stat origin/main...HEAD
git diff origin/main...HEAD -- apps/api/control apps/web mcp docs/migration-runbook.md
```

Confirm there is no code that writes systemd unit files, modifies `ExecStart`, changes workload `WorkingDirectory`, performs a `configured -> managed` transition, or creates a new Agent operation kind.

- [ ] **Step 6: Commit the runbook**

```bash
git add docs/migration-runbook.md
git commit -m "docs: add stage B2 adoption rollout"
```

- [ ] **Step 7: Record integration evidence before production**

Capture:

```bash
git status --short --branch
git log --oneline --decorate -8
git rev-parse HEAD
```

Require a clean working tree and retain the exact final commit SHA for production rollout.

---

## Acceptance Checklist

Before declaring Stage B2 complete, verify every item against runtime evidence:

- [ ] Existing Service rows migrated to `managed` with old-compatible `unit_name`.
- [ ] Managed create still requires complete deployment metadata.
- [ ] A real `ServiceSnapshot` unit can be adopted into a Project.
- [ ] Adoption persists real server/unit binding and state `adopted`.
- [ ] Adoption creates no `Operation`.
- [ ] Duplicate server/unit and duplicate project/name are rejected safely.
- [ ] Protected unit can be adopted but remains protected from typed mutation policy.
- [ ] Missing later inventory reports `inventory_status=missing` without deleting Service/audit history.
- [ ] Complete configuration moves `adopted -> configured` and creates no `Operation`.
- [ ] Partial/invalid configuration is rejected.
- [ ] Managed service is rejected by the Stage B2 configuration endpoint.
- [ ] Adopted/configured deploy is blocked with `service_not_managed` before any Deployment/Operation is created.
- [ ] Redeploy/rollback are blocked for non-managed services.
- [ ] GitHub webhook deployment is blocked for non-managed services.
- [ ] Managed deployment execution uses persisted `service.unit_name`.
- [ ] Existing managed deployment/redeploy/rollback tests remain green.
- [ ] MCP exposes exactly two new typed Stage B2 tools and no takeover tool.
- [ ] Web Project page can adopt inventory units and labels protected/bound state correctly.
- [ ] Web Service page hides Deploy for adopted/configured and preserves it for managed.
- [ ] Web visibly reports missing inventory without deleting the service.
- [ ] No Agent operation kind/capability is added for Stage B2.
- [ ] No `configured -> managed` transition exists.
- [ ] Production acceptance uses metadata-only adoption and causes no workload restart/downtime.
