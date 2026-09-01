# DigitalAfarin VPS MCP Multi-Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing single-server VPS MVP into a backward-compatible multi-server control plane whose outbound host agents report to Django and whose read-only state is available to ChatGPT through a localhost-only MCP server and the already-created OpenAI Secure MCP Tunnel.

**Architecture:** Django remains the system of record and authorization boundary. Each VPS receives an independent revocable agent credential and pushes metrics/service inventory outbound to Django; the MCP service never contacts agents or PostgreSQL directly and reads only scoped Django REST endpoints. The existing integer Django primary key and pull/sync path remain temporarily for compatibility, while a UUID `public_id` becomes the stable external server identity and is serialized as API field `id`.

**Tech Stack:** Python 3.12+, Django 5.2 LTS, Django REST Framework 3.16+, PostgreSQL/SQLite for tests, FastAPI host agent, httpx, official MCP Python SDK v2 (`mcp>=2,<3`), pytest for agent/MCP tests, Django `TestCase`/DRF `APITestCase` for API tests, systemd, OpenAI Secure MCP Tunnel.

**Spec:** `docs/superpowers/specs/2026-09-01-vps-mcp-multiserver-design.md`

## Global Constraints

- MCP milestone v1 is read-only: no start, stop, restart, deploy, rollback, Nginx mutation, backup mutation, or arbitrary shell execution.
- Host agents use outbound HTTPS to Django; secondary VPS hosts expose no inbound agent port to the internet.
- MCP binds only to `127.0.0.1:3060` and serves Streamable HTTP at `/mcp`.
- Use the current stable MCP Python SDK v2 line: dependency `mcp>=2,<3`; do not use v1 APIs.
- OpenAI Secure MCP Tunnel is the only supported external bridge to the local MCP endpoint.
- Agent heartbeat interval is 15 seconds; server state is stale after 45 seconds and offline after 120 seconds.
- Every server has an independent revocable agent credential; Django stores only one-way SHA-256 digests of 256-bit random bearer secrets.
- MCP uses a separate scoped service principal with `servers:read`, `metrics:read`, `services:read`, and `audit:read`.
- No secret token, Authorization header, raw traceback, database credential, Django `SECRET_KEY`, or agent credential may appear in API/MCP output or audit metadata.
- Host service inventory remains constrained by the existing local `AGENT_SERVICE_PREFIXES` allow-list.
- Keep legacy `Server.agent_url`, `AgentClient`, `/api/servers/{pk}/sync/`, `PLATFORM_AGENT_TOKEN`, and the local read-only FastAPI endpoints working during this milestone; mark them deprecated in docs only after outbound heartbeat passes acceptance.
- For migration safety, keep the current integer database PK internal during Stage A. Add `Server.public_id: UUID` and expose it as JSON `id`; all new agent/control/MCP routes use the UUID. A physical PK rewrite is deferred because it adds migration risk without changing the external contract.
- Do not add the future `Operation` write model in this plan; the spec explicitly permits deferring it and YAGNI favors a separate approved write milestone.

---

## File Structure Map

### Django control plane

- `apps/api/control/models.py` — multi-server identity, credentials, service principals, freshness rules.
- `apps/api/control/security.py` — high-entropy token issuing, parsing, hashing, constant-time digest comparison.
- `apps/api/control/authentication.py` — keep legacy browser/platform auth and add agent/service-principal authentication.
- `apps/api/control/permissions.py` — scope-based DRF permission helper.
- `apps/api/control/agent_serializers.py` — enrollment and heartbeat request/response validation.
- `apps/api/control/control_serializers.py` — read-only public server/metrics/service/audit response shapes.
- `apps/api/control/services/enrollment.py` — one-time enrollment transaction.
- `apps/api/control/services/heartbeat.py` — heartbeat transaction, freshness/audit behavior, service snapshot reconciliation.
- `apps/api/control/services/server_resolution.py` — UUID/default server resolution shared by control views.
- `apps/api/control/agent_views.py` / `agent_urls.py` — `/api/agent/v1/enroll` and `/heartbeat`.
- `apps/api/control/control_views.py` / `control_urls.py` — stable scoped read API used by MCP.
- `apps/api/control/management/commands/create_enrollment_token.py` — operator enrollment secret, shown once.
- `apps/api/control/management/commands/create_service_principal.py` — MCP principal + secret, shown once.
- `apps/api/control/migrations/0002_multiserver_identity.py` — additive schema only.
- `apps/api/control/tests/` — model/security/agent/control API tests.

### Host agent

- `agent/digitalafarin_agent/config.py` — optional legacy token plus control-plane/outbound settings.
- `agent/digitalafarin_agent/control_plane.py` — enrollment and heartbeat HTTP client.
- `agent/digitalafarin_agent/identity.py` — secure local credential-file read/write.
- `agent/digitalafarin_agent/heartbeat.py` — build snapshot payload and periodic runner.
- `agent/digitalafarin_agent/main.py` — preserve legacy API and start outbound runner via FastAPI lifespan when configured.
- `agent/tests/` — identity/client/heartbeat tests.

### MCP service

- `mcp/pyproject.toml` — isolated MCP package and dependencies.
- `mcp/digitalafarin_vps_mcp/config.py` — control-plane URL/token and local bind settings.
- `mcp/digitalafarin_vps_mcp/errors.py` — sanitized domain errors.
- `mcp/digitalafarin_vps_mcp/control_plane.py` — async scoped REST client.
- `mcp/digitalafarin_vps_mcp/server.py` — `MCPServer`, six read-only tools, localhost Streamable HTTP runner.
- `mcp/tests/` — in-memory MCP tool contract/error tests.

### Deployment/docs

- `.env.example` — new server-side variables without secret values.
- `infra/systemd/digitalafarin-platform-agent.service` — canonical outbound-agent unit after renaming the existing agent unit.
- `infra/systemd/digitalafarin-platform-api.service` — canonical API unit after renaming the existing API unit.
- `infra/systemd/digitalafarin-platform-web.service` — canonical web unit after renaming the existing web unit.
- `infra/systemd/digitalafarin-platform-mcp.service` — local MCP service.
- `infra/systemd/digitalafarin-platform-mcp-tunnel.service` — tunnel profile service.
- `README.md` — multi-server enrollment + local acceptance workflow and legacy deprecation note.

---

### Task 1: Add stable multi-server identity and freshness semantics

**Files:**
- Modify: `apps/api/control/models.py`
- Create: `apps/api/control/migrations/0002_multiserver_identity.py`
- Create: `apps/api/control/tests/__init__.py`
- Create: `apps/api/control/tests/test_server_model.py`

**Interfaces:**
- Consumes: existing `Server`, `ServiceSnapshot`, `AuditEvent` models.
- Produces: `Server.public_id: UUID`, `Server.is_default`, `Server.agent_version`, `Server.capabilities` (JSON array of strings), `Server.status`, `Server.age_seconds`, `Server.is_stale`, and one-active-default database invariant. New APIs in later tasks use `public_id` as their external `id`.

- [ ] **Step 1: Write failing model tests for UUID identity, freshness, and default uniqueness**

```python
# apps/api/control/tests/test_server_model.py
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from control.models import Server


class ServerModelTests(TestCase):
    def test_public_id_is_uuid_and_unique(self):
        first = Server.objects.create(name="primary")
        second = Server.objects.create(name="secondary")
        self.assertNotEqual(first.public_id, second.public_id)
        self.assertEqual(str(first.public_id), str(first.public_id))

    def test_status_is_derived_from_last_seen(self):
        now = timezone.now()
        server = Server.objects.create(name="primary", last_seen_at=now - timedelta(seconds=10))
        self.assertEqual(server.status_at(now), "online")
        server.last_seen_at = now - timedelta(seconds=60)
        self.assertEqual(server.status_at(now), "stale")
        server.last_seen_at = now - timedelta(seconds=121)
        self.assertEqual(server.status_at(now), "offline")

    def test_only_one_active_default_is_allowed(self):
        Server.objects.create(name="primary", is_active=True, is_default=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Server.objects.create(name="secondary", is_active=True, is_default=True)
```

- [ ] **Step 2: Run the model tests and verify they fail**

Run:

```bash
cd apps/api
python manage.py test control.tests.test_server_model -v 2
```

Expected: FAIL because `public_id`, `is_default`, and `status_at()` do not exist.

- [ ] **Step 3: Add the additive fields and derived freshness methods**

```python
# additions to apps/api/control/models.py
import uuid
from datetime import datetime

from django.db import models
from django.db.models import Q
from django.utils import timezone


class Server(models.Model):
    # Keep the existing integer `id`/PK until the pull path is retired.
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120)
    hostname = models.CharField(max_length=255, blank=True)
    agent_url = models.URLField(default="http://127.0.0.1:9743")
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    agent_version = models.CharField(max_length=64, blank=True)
    capabilities = models.JSONField(default=list, blank=True)
    cpu_percent = models.FloatField(default=0)
    memory_percent = models.FloatField(default=0)
    disk_percent = models.FloatField(default=0)
    uptime_seconds = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True, is_active=True),
                name="uniq_active_default_server",
            )
        ]

    def age_seconds_at(self, now: datetime | None = None) -> int | None:
        if self.last_seen_at is None:
            return None
        current = now or timezone.now()
        return max(0, int((current - self.last_seen_at).total_seconds()))

    def status_at(self, now: datetime | None = None) -> str:
        age = self.age_seconds_at(now)
        if age is None or age > 120:
            return "offline"
        if age > 45:
            return "stale"
        return "online"

    @property
    def status(self) -> str:
        return self.status_at()

    @property
    def age_seconds(self) -> int | None:
        return self.age_seconds_at()

    @property
    def is_stale(self) -> bool:
        return self.status != "online"
```

Create the migration with Django rather than hand-editing SQL:

```bash
cd apps/api
python manage.py makemigrations control --name multiserver_identity
```

Open the generated migration and verify it is additive: `public_id`, `is_default`, `agent_version`, `capabilities`, and `uniq_active_default_server`; it must not remove or alter `agent_url` or the existing integer PK.

- [ ] **Step 4: Run migration checks and model tests**

Run:

```bash
cd apps/api
python manage.py migrate
python manage.py test control.tests.test_server_model -v 2
python manage.py check
```

Expected: all PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add apps/api/control/models.py apps/api/control/migrations apps/api/control/tests
git commit -m "feat: add multi-server identity and freshness"
```

---

### Task 2: Add one-time enrollment and independent agent credentials

**Files:**
- Modify: `apps/api/control/models.py`
- Create: `apps/api/control/security.py`
- Create: `apps/api/control/services/enrollment.py`
- Create: `apps/api/control/management/commands/create_enrollment_token.py`
- Create: `apps/api/control/management/commands/revoke_agent_credentials.py`
- Create: `apps/api/control/migrations/0003_agent_credentials.py`
- Create: `apps/api/control/tests/test_security.py`
- Create: `apps/api/control/tests/test_enrollment_service.py`

**Interfaces:**
- Consumes: `Server.public_id` from Task 1.
- Produces: `EnrollmentToken`, `AgentCredential`, `issue_secret(kind) -> IssuedSecret`, `parse_secret(value, expected_kind) -> tuple[prefix, secret]`, `verify_secret(secret, digest) -> bool`, and `enroll_agent(*, enrollment_secret: str, name: str, hostname: str, agent_version: str, capabilities: list[str]) -> EnrollmentResult`.

- [ ] **Step 1: Write failing token and enrollment-service tests**

```python
# apps/api/control/tests/test_security.py
from django.test import SimpleTestCase
from control.security import issue_secret, parse_secret, verify_secret


class SecurityTests(SimpleTestCase):
    def test_agent_secret_round_trip(self):
        issued = issue_secret("agent")
        prefix, secret = parse_secret(issued.cleartext, "agent")
        self.assertEqual(prefix, issued.prefix)
        self.assertTrue(verify_secret(secret, issued.digest))
        self.assertFalse(verify_secret(secret + "x", issued.digest))

    def test_wrong_kind_is_rejected(self):
        issued = issue_secret("enroll")
        with self.assertRaises(ValueError):
            parse_secret(issued.cleartext, "agent")
```

```python
# apps/api/control/tests/test_enrollment_service.py
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from control.models import EnrollmentToken
from control.security import issue_secret
from control.services.enrollment import EnrollmentError, enroll_agent


class EnrollmentServiceTests(TestCase):
    def setUp(self):
        issued = issue_secret("enroll")
        self.secret = issued.cleartext
        self.row = EnrollmentToken.objects.create(
            token_prefix=issued.prefix,
            secret_hash=issued.digest,
            expires_at=timezone.now() + timedelta(minutes=10),
            created_by="test",
        )

    def test_enrollment_returns_server_specific_secret_once(self):
        result = enroll_agent(
            enrollment_secret=self.secret,
            name="VPS One",
            hostname="vps-one",
            agent_version="0.2.0",
            capabilities=["metrics", "systemd_inventory"],
        )
        self.assertIsNotNone(result.server.public_id)
        self.assertTrue(result.agent_token.startswith("da_agent_"))
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.used_at)

        with self.assertRaises(EnrollmentError):
            enroll_agent(
                enrollment_secret=self.secret,
                name="VPS Two",
                hostname="vps-two",
                agent_version="0.2.0",
                capabilities=[],
            )
```

- [ ] **Step 2: Run tests and verify missing symbols/models fail**

```bash
cd apps/api
python manage.py test control.tests.test_security control.tests.test_enrollment_service -v 2
```

Expected: FAIL because credential models/security helpers do not exist.

- [ ] **Step 3: Implement token primitives and credential models**

```python
# apps/api/control/security.py
from dataclasses import dataclass
import hashlib
import secrets

_ALLOWED_KINDS = {"enroll", "agent", "service"}


@dataclass(frozen=True)
class IssuedSecret:
    cleartext: str
    prefix: str
    digest: str


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def issue_secret(kind: str) -> IssuedSecret:
    if kind not in _ALLOWED_KINDS:
        raise ValueError("unsupported secret kind")
    prefix = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)  # 256 bits before URL-safe encoding
    return IssuedSecret(
        cleartext=f"da_{kind}_{prefix}.{secret}",
        prefix=prefix,
        digest=_digest(secret),
    )


def parse_secret(value: str, expected_kind: str) -> tuple[str, str]:
    marker = f"da_{expected_kind}_"
    if not value.startswith(marker) or "." not in value:
        raise ValueError("invalid secret format")
    prefix, secret = value[len(marker):].split(".", 1)
    if not prefix or not secret:
        raise ValueError("invalid secret format")
    return prefix, secret


def verify_secret(secret: str, digest: str) -> bool:
    return secrets.compare_digest(_digest(secret), digest)
```

```python
# additions to apps/api/control/models.py
class EnrollmentToken(models.Model):
    token_prefix = models.CharField(max_length=32, unique=True)
    secret_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)


class AgentCredential(models.Model):
    server = models.ForeignKey(Server, related_name="agent_credentials", on_delete=models.CASCADE)
    token_prefix = models.CharField(max_length=32, unique=True)
    token_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
```

Generate migration:

```bash
cd apps/api
python manage.py makemigrations control --name agent_credentials
```

- [ ] **Step 4: Implement transactional enrollment service**

```python
# apps/api/control/services/enrollment.py
from dataclasses import dataclass
from django.db import transaction
from django.utils import timezone

from control.models import AgentCredential, AuditEvent, EnrollmentToken, Server
from control.security import issue_secret, parse_secret, verify_secret


class EnrollmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnrollmentResult:
    server: Server
    agent_token: str


@transaction.atomic
def enroll_agent(*, enrollment_secret: str, name: str, hostname: str,
                 agent_version: str, capabilities: list[str]) -> EnrollmentResult:
    try:
        prefix, secret = parse_secret(enrollment_secret, "enroll")
        token = EnrollmentToken.objects.select_for_update().get(token_prefix=prefix)
    except (ValueError, EnrollmentToken.DoesNotExist) as exc:
        raise EnrollmentError("invalid enrollment credential") from exc

    now = timezone.now()
    if token.used_at is not None or token.expires_at <= now or not verify_secret(secret, token.secret_hash):
        raise EnrollmentError("invalid enrollment credential")

    server = Server.objects.create(
        name=name,
        hostname=hostname,
        agent_version=agent_version,
        capabilities=capabilities,
    )
    issued = issue_secret("agent")
    AgentCredential.objects.create(
        server=server,
        token_prefix=issued.prefix,
        token_hash=issued.digest,
    )
    token.used_at = now
    token.save(update_fields=["used_at"])
    AuditEvent.objects.create(
        event_type="agent.enrolled",
        target_type="server",
        target_id=str(server.public_id),
        actor="enrollment",
        metadata={"hostname": hostname},
    )
    return EnrollmentResult(server=server, agent_token=issued.cleartext)
```

- [ ] **Step 5: Add operator command that prints the clear enrollment secret exactly once**

```python
# apps/api/control/management/commands/create_enrollment_token.py
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from control.models import EnrollmentToken
from control.security import issue_secret


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=15)
        parser.add_argument("--created-by", default="operator")

    def handle(self, *args, **options):
        issued = issue_secret("enroll")
        EnrollmentToken.objects.create(
            token_prefix=issued.prefix,
            secret_hash=issued.digest,
            expires_at=timezone.now() + timedelta(minutes=options["minutes"]),
            created_by=options["created_by"],
        )
        self.stdout.write(issued.cleartext)
```

- [ ] **Step 6: Add a revocation command that immediately disables a server's active agent credentials and audits it**

```python
# apps/api/control/management/commands/revoke_agent_credentials.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from control.models import AgentCredential, AuditEvent, Server


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("server_id")
        parser.add_argument("--actor", default="operator")

    def handle(self, *args, **options):
        try:
            server = Server.objects.get(public_id=options["server_id"])
        except (ValueError, Server.DoesNotExist) as exc:
            raise CommandError("server not found") from exc
        now = timezone.now()
        count = AgentCredential.objects.filter(server=server, revoked_at__isnull=True).update(revoked_at=now)
        AuditEvent.objects.create(
            event_type="agent.credential.revoked",
            target_type="server",
            target_id=str(server.public_id),
            actor=options["actor"],
            metadata={"credential_count": count},
        )
        self.stdout.write(str(count))
```

- [ ] **Step 7: Run migrations/tests and verify stored rows do not contain cleartext secrets**

```bash
cd apps/api
python manage.py migrate
python manage.py test control.tests.test_security control.tests.test_enrollment_service -v 2
python manage.py create_enrollment_token --minutes 1 --created-by test-operator
```

Expected: tests PASS; command prints one value in format `da_enroll_<prefix>.<secret>`. Verify DB fields are `token_prefix` + 64-char hash only via Django shell, not by printing the clear secret again.

- [ ] **Step 8: Commit Task 2**

```bash
git add apps/api/control
 git commit -m "feat: add agent enrollment credentials"
```

---

### Task 3: Add authenticated outbound heartbeat ingestion

**Files:**
- Modify: `apps/api/control/authentication.py`
- Create: `apps/api/control/agent_serializers.py`
- Create: `apps/api/control/services/heartbeat.py`
- Create: `apps/api/control/agent_views.py`
- Create: `apps/api/control/agent_urls.py`
- Modify: `apps/api/platform_api/urls.py`
- Create: `apps/api/control/tests/test_agent_api.py`

**Interfaces:**
- Consumes: `AgentCredential`, `enroll_agent()`, `ServiceSnapshot`.
- Produces: `POST /api/agent/v1/enroll`, `POST /api/agent/v1/heartbeat`, `AgentPrincipal.server`, and `apply_heartbeat(server, payload) -> Server`.

- [ ] **Step 1: Write failing API tests for enrollment, isolation, heartbeat, and revocation**

```python
# apps/api/control/tests/test_agent_api.py
from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import AgentCredential, EnrollmentToken, Server
from control.security import issue_secret


class AgentAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        issued = issue_secret("enroll")
        self.enrollment_secret = issued.cleartext
        EnrollmentToken.objects.create(
            token_prefix=issued.prefix,
            secret_hash=issued.digest,
            expires_at=timezone.now() + timedelta(minutes=10),
            created_by="test",
        )

    def enroll(self):
        response = self.client.post(
            "/api/agent/v1/enroll",
            {
                "name": "VPS One",
                "hostname": "vps-one",
                "agent_version": "0.2.0",
                "capabilities": ["metrics", "systemd_inventory"],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.enrollment_secret}",
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_heartbeat_updates_only_authenticated_server(self):
        enrolled = self.enroll()
        other = Server.objects.create(name="Other")
        response = self.client.post(
            "/api/agent/v1/heartbeat",
            {
                "agent_version": "0.2.0",
                "hostname": "vps-one",
                "capabilities": ["metrics", "systemd_inventory"],
                "metrics": {"cpu_percent": 12.5, "memory_percent": 40.0, "disk_percent": 25.0, "uptime_seconds": 100},
                "services": [{"unit_name": "digitalafarin-platform-api.service", "description": "API", "load_state": "loaded", "active_state": "active", "sub_state": "running"}],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {enrolled['agent_token']}",
        )
        self.assertEqual(response.status_code, 204)
        server = Server.objects.get(public_id=enrolled["server_id"])
        self.assertEqual(server.cpu_percent, 12.5)
        self.assertEqual(server.services.count(), 1)
        other.refresh_from_db()
        self.assertIsNone(other.last_seen_at)

    def test_revoked_credential_cannot_heartbeat(self):
        enrolled = self.enroll()
        credential = AgentCredential.objects.get(server__public_id=enrolled["server_id"])
        credential.revoked_at = timezone.now()
        credential.save(update_fields=["revoked_at"])
        response = self.client.post(
            "/api/agent/v1/heartbeat",
            {"agent_version": "0.2.0", "hostname": "vps-one", "capabilities": [], "metrics": {"cpu_percent": 1, "memory_percent": 1, "disk_percent": 1, "uptime_seconds": 1}, "services": []},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {enrolled['agent_token']}",
        )
        self.assertEqual(response.status_code, 401)
```

- [ ] **Step 2: Run the test and confirm the new routes fail**

```bash
cd apps/api
python manage.py test control.tests.test_agent_api -v 2
```

Expected: FAIL/404 for `/api/agent/v1/*`.

- [ ] **Step 3: Implement dedicated agent authentication**

```python
# additions to apps/api/control/authentication.py
from django.utils import timezone
from control.models import AgentCredential
from control.security import parse_secret, verify_secret


class AgentPrincipal:
    is_authenticated = True

    def __init__(self, credential: AgentCredential):
        self.credential = credential
        self.server = credential.server
        self.username = f"agent:{self.server.public_id}"

    def __str__(self):
        return self.username


class AgentTokenAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        raw = request.headers.get("Authorization", "")
        if not raw.startswith("Bearer "):
            raise exceptions.AuthenticationFailed("Invalid agent credential")
        try:
            prefix, secret = parse_secret(raw[7:].strip(), "agent")
            credential = AgentCredential.objects.select_related("server").get(
                token_prefix=prefix,
                revoked_at__isnull=True,
                server__is_active=True,
            )
        except (ValueError, AgentCredential.DoesNotExist) as exc:
            raise exceptions.AuthenticationFailed("Invalid agent credential") from exc
        if not verify_secret(secret, credential.token_hash):
            raise exceptions.AuthenticationFailed("Invalid agent credential")
        credential.last_used_at = timezone.now()
        credential.save(update_fields=["last_used_at"])
        return AgentPrincipal(credential), credential
```

- [ ] **Step 4: Implement strict serializers and heartbeat transaction**

```python
# apps/api/control/agent_serializers.py
from rest_framework import serializers


class EnrollRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    hostname = serializers.CharField(max_length=255)
    agent_version = serializers.CharField(max_length=64)
    capabilities = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)


class MetricsSerializer(serializers.Serializer):
    cpu_percent = serializers.FloatField(min_value=0, max_value=100)
    memory_percent = serializers.FloatField(min_value=0, max_value=100)
    disk_percent = serializers.FloatField(min_value=0, max_value=100)
    uptime_seconds = serializers.IntegerField(min_value=0)


class ServiceHeartbeatSerializer(serializers.Serializer):
    unit_name = serializers.RegexField(r"^[A-Za-z0-9_.@:-]+$", max_length=255)
    description = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")
    load_state = serializers.CharField(max_length=32)
    active_state = serializers.CharField(max_length=32)
    sub_state = serializers.CharField(max_length=32)


class HeartbeatRequestSerializer(serializers.Serializer):
    agent_version = serializers.CharField(max_length=64)
    hostname = serializers.CharField(max_length=255)
    capabilities = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)
    metrics = MetricsSerializer()
    services = ServiceHeartbeatSerializer(many=True)
```

```python
# apps/api/control/services/heartbeat.py
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from control.models import AuditEvent, Server, ServiceSnapshot


@transaction.atomic
def apply_heartbeat(server: Server, payload: dict) -> Server:
    now = timezone.now()
    metrics = payload["metrics"]
    server.hostname = payload["hostname"]
    server.agent_version = payload["agent_version"]
    server.capabilities = payload["capabilities"]
    server.cpu_percent = metrics["cpu_percent"]
    server.memory_percent = metrics["memory_percent"]
    server.disk_percent = metrics["disk_percent"]
    server.uptime_seconds = metrics["uptime_seconds"]
    server.last_seen_at = now
    server.save(update_fields=[
        "hostname", "agent_version", "capabilities", "cpu_percent", "memory_percent",
        "disk_percent", "uptime_seconds", "last_seen_at", "updated_at",
    ])

    seen: set[str] = set()
    for item in payload["services"]:
        seen.add(item["unit_name"])
        ServiceSnapshot.objects.update_or_create(
            server=server,
            unit_name=item["unit_name"],
            defaults={
                "description": item.get("description", ""),
                "load_state": item["load_state"],
                "active_state": item["active_state"],
                "sub_state": item["sub_state"],
            },
        )
    server.services.exclude(unit_name__in=seen).delete()

    # Sample the high-frequency heartbeat audit to one durable event per five minutes/server.
    recent = AuditEvent.objects.filter(
        event_type="agent.heartbeat.accepted",
        target_type="server",
        target_id=str(server.public_id),
        created_at__gte=now - timedelta(minutes=5),
    ).exists()
    if not recent:
        AuditEvent.objects.create(
            event_type="agent.heartbeat.accepted",
            target_type="server",
            target_id=str(server.public_id),
            actor=f"agent:{server.public_id}",
            metadata={"service_count": len(seen)},
        )
    return server
```

- [ ] **Step 5: Add enrollment/heartbeat views with per-view authentication and generic failures**

```python
# apps/api/control/agent_views.py
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from control.agent_serializers import EnrollRequestSerializer, HeartbeatRequestSerializer
from control.authentication import AgentTokenAuthentication
from control.services.enrollment import EnrollmentError, enroll_agent
from control.services.heartbeat import apply_heartbeat


def _bearer(request) -> str:
    raw = request.headers.get("Authorization", "")
    if not raw.startswith("Bearer "):
        return ""
    return raw[7:].strip()


class EnrollView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EnrollRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = enroll_agent(enrollment_secret=_bearer(request), **serializer.validated_data)
        except EnrollmentError:
            return Response({"detail": "Invalid enrollment credential"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(
            {"server_id": str(result.server.public_id), "agent_token": result.agent_token},
            status=status.HTTP_201_CREATED,
        )


class HeartbeatView(APIView):
    authentication_classes = [AgentTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = HeartbeatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        apply_heartbeat(request.user.server, serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)
```

```python
# apps/api/control/agent_urls.py
from django.urls import path
from control.agent_views import EnrollView, HeartbeatView

urlpatterns = [
    path("enroll", EnrollView.as_view(), name="agent-enroll"),
    path("heartbeat", HeartbeatView.as_view(), name="agent-heartbeat"),
]
```

Add before legacy `/api/` include:

```python
# apps/api/platform_api/urls.py
path("api/agent/v1/", include("control.agent_urls")),
```

- [ ] **Step 6: Run API tests and full Django checks**

```bash
cd apps/api
python manage.py test control.tests -v 2
python manage.py check
```

Expected: PASS; agent API uses UUID server identity and cannot modify another server.

- [ ] **Step 7: Commit Task 3**

```bash
git add apps/api/control apps/api/platform_api/urls.py
git commit -m "feat: ingest authenticated agent heartbeats"
```

---

### Task 4: Add scoped MCP service principal and stable read-only control API

**Files:**
- Modify: `apps/api/control/models.py`
- Modify: `apps/api/control/authentication.py`
- Create: `apps/api/control/permissions.py`
- Create: `apps/api/control/control_serializers.py`
- Create: `apps/api/control/services/server_resolution.py`
- Create: `apps/api/control/control_views.py`
- Create: `apps/api/control/control_urls.py`
- Create: `apps/api/control/management/commands/create_service_principal.py`
- Create: `apps/api/control/migrations/0004_service_principals.py`
- Modify: `apps/api/platform_api/urls.py`
- Create: `apps/api/control/tests/test_control_api.py`

**Interfaces:**
- Consumes: `Server.public_id`, freshness properties, `ServiceSnapshot`, `AuditEvent`.
- Produces: `ServicePrincipal`, `ServiceCredential`, `ServicePrincipalAuthentication`, `require_scope(scope)`, `resolve_server(identifier)`, and `/api/control/v1/*` read endpoints. `identifier` accepts a UUID string or literal `default`.

- [ ] **Step 1: Write failing tests for scopes, default resolution, read bounds, and UUID output**

```python
# apps/api/control/tests/test_control_api.py
from django.test import TestCase
from rest_framework.test import APIClient

from control.models import Server, ServiceCredential, ServicePrincipal, ServiceSnapshot
from control.security import issue_secret


class ControlAPITests(TestCase):
    def setUp(self):
        self.server = Server.objects.create(name="Primary", hostname="primary", is_default=True)
        ServiceSnapshot.objects.create(
            server=self.server,
            unit_name="digitalafarin-platform-api.service",
            description="API",
            load_state="loaded",
            active_state="active",
            sub_state="running",
        )
        principal = ServicePrincipal.objects.create(
            name="chatgpt-vps-mcp",
            scopes=["servers:read", "metrics:read", "services:read", "audit:read"],
        )
        issued = issue_secret("service")
        ServiceCredential.objects.create(
            principal=principal,
            token_prefix=issued.prefix,
            token_hash=issued.digest,
        )
        self.token = issued.cleartext
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def test_default_server_uses_uuid_external_id(self):
        response = self.client.get("/api/control/v1/servers/default/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.server.public_id))
        self.assertNotIn("agent_url", response.json())

    def test_service_list_is_server_scoped(self):
        response = self.client.get("/api/control/v1/servers/default/services/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["unit_name"], "digitalafarin-platform-api.service")

    def test_metrics_unavailable_before_first_heartbeat(self):
        response = self.client.get("/api/control/v1/servers/default/metrics/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "metrics_unavailable")

    def test_missing_scope_is_forbidden(self):
        principal = ServicePrincipal.objects.get(name="chatgpt-vps-mcp")
        principal.scopes = ["servers:read"]
        principal.save(update_fields=["scopes"])
        response = self.client.get("/api/control/v1/servers/default/metrics/")
        self.assertEqual(response.status_code, 403)
```

- [ ] **Step 2: Run tests and confirm missing models/routes fail**

```bash
cd apps/api
python manage.py test control.tests.test_control_api -v 2
```

Expected: FAIL because service principals/control routes do not exist.

- [ ] **Step 3: Add service-principal models, authentication, and scope permission factory**

```python
# additions to apps/api/control/models.py
class ServicePrincipal(models.Model):
    name = models.CharField(max_length=120, unique=True)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ServiceCredential(models.Model):
    principal = models.ForeignKey(ServicePrincipal, related_name="credentials", on_delete=models.CASCADE)
    token_prefix = models.CharField(max_length=32, unique=True)
    token_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
```

```python
# additions to apps/api/control/authentication.py
class ServicePrincipalAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        raw = request.headers.get("Authorization", "")
        if not raw.startswith("Bearer "):
            raise exceptions.AuthenticationFailed("Invalid service credential")
        try:
            prefix, secret = parse_secret(raw[7:].strip(), "service")
            credential = ServiceCredential.objects.select_related("principal").get(
                token_prefix=prefix,
                revoked_at__isnull=True,
                principal__is_active=True,
            )
        except (ValueError, ServiceCredential.DoesNotExist) as exc:
            raise exceptions.AuthenticationFailed("Invalid service credential") from exc
        if not verify_secret(secret, credential.token_hash):
            raise exceptions.AuthenticationFailed("Invalid service credential")
        credential.last_used_at = timezone.now()
        credential.save(update_fields=["last_used_at"])
        return ServicePrincipalUser(credential.principal), credential


class ServicePrincipalUser:
    is_authenticated = True

    def __init__(self, principal):
        self.principal = principal
        self.name = principal.name
        self.username = principal.name
        self.scopes = principal.scopes

    def __str__(self):
        return self.name
```

```python
# apps/api/control/permissions.py
from rest_framework.permissions import BasePermission


def require_scope(scope: str):
    class ScopePermission(BasePermission):
        def has_permission(self, request, view):
            scopes = set(getattr(request.user, "scopes", []))
            return scope in scopes
    ScopePermission.__name__ = f"Require_{scope.replace(':', '_')}"
    return ScopePermission
```

Generate and apply migration:

```bash
cd apps/api
python manage.py makemigrations control --name service_principals
python manage.py migrate
```

- [ ] **Step 4: Implement deterministic server resolution**

```python
# apps/api/control/services/server_resolution.py
import uuid
from control.models import Server


class ServerResolutionError(RuntimeError):
    code = "server_not_found"


class DefaultServerNotConfigured(ServerResolutionError):
    code = "default_server_not_configured"


def resolve_server(identifier: str) -> Server:
    if identifier == "default":
        server = Server.objects.filter(is_active=True, is_default=True).first()
        if server is None:
            raise DefaultServerNotConfigured("Default server is not configured")
        return server
    try:
        public_id = uuid.UUID(identifier)
    except ValueError as exc:
        raise ServerResolutionError("Server does not exist") from exc
    try:
        return Server.objects.get(public_id=public_id, is_active=True)
    except Server.DoesNotExist as exc:
        raise ServerResolutionError("Server does not exist") from exc
```

- [ ] **Step 5: Add safe serializers that never expose `agent_url` or credentials**

```python
# apps/api/control/control_serializers.py
from rest_framework import serializers
from control.models import AuditEvent, Server, ServiceSnapshot


class ServerReadSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status = serializers.CharField(read_only=True)
    age_seconds = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Server
        fields = ["id", "name", "hostname", "is_default", "status", "last_seen_at", "age_seconds", "agent_version", "capabilities"]


class MetricsReadSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status = serializers.CharField(read_only=True)
    age_seconds = serializers.IntegerField(read_only=True, allow_null=True)
    stale = serializers.BooleanField(source="is_stale", read_only=True)
    collected_at = serializers.DateTimeField(source="last_seen_at", read_only=True, allow_null=True)

    class Meta:
        model = Server
        fields = ["id", "name", "status", "cpu_percent", "memory_percent", "disk_percent", "uptime_seconds", "collected_at", "age_seconds", "stale"]


class ServiceReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceSnapshot
        fields = ["unit_name", "description", "load_state", "active_state", "sub_state", "last_seen_at"]


class AuditReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["event_type", "target_type", "target_id", "actor", "metadata", "created_at"]
```

- [ ] **Step 6: Implement scoped read endpoints and MCP read-audit events**

Use APIViews with explicit authentication/permission per endpoint. Required paths:

```python
# apps/api/control/control_urls.py
from django.urls import path
from control import control_views

urlpatterns = [
    path("servers/", control_views.ServerListView.as_view()),
    path("servers/<str:server_id>/", control_views.ServerDetailView.as_view()),
    path("servers/<str:server_id>/metrics/", control_views.ServerMetricsView.as_view()),
    path("servers/<str:server_id>/services/", control_views.ServiceListView.as_view()),
    path("servers/<str:server_id>/services/<path:unit_name>/", control_views.ServiceDetailView.as_view()),
    path("audit/", control_views.AuditListView.as_view()),
]
```

Implement the views with a shared base and explicit scope classes:

```python
# apps/api/control/control_views.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from control.authentication import ServicePrincipalAuthentication
from control.control_serializers import AuditReadSerializer, MetricsReadSerializer, ServerReadSerializer, ServiceReadSerializer
from control.models import AuditEvent, Server
from control.permissions import require_scope
from control.services.server_resolution import DefaultServerNotConfigured, ServerResolutionError, resolve_server


def _error(exc):
    if isinstance(exc, DefaultServerNotConfigured):
        return Response({"error": exc.code, "message": "Default server is not configured."}, status=status.HTTP_409_CONFLICT)
    return Response({"error": "server_not_found", "message": "The requested server does not exist."}, status=status.HTTP_404_NOT_FOUND)


def _audit(request, event_type: str, server=None, metadata=None):
    AuditEvent.objects.create(
        event_type=event_type,
        target_type="server" if server else "control",
        target_id=str(server.public_id) if server else "",
        actor=request.user.name,
        metadata=metadata or {},
    )


class ControlAPIView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]


class ServerListView(ControlAPIView):
    permission_classes = [require_scope("servers:read")]
    def get(self, request):
        items = Server.objects.filter(is_active=True).order_by("name")
        _audit(request, "mcp.servers.read", metadata={"count": items.count()})
        return Response({"items": ServerReadSerializer(items, many=True).data})


class ServerDetailView(ControlAPIView):
    permission_classes = [require_scope("servers:read")]
    def get(self, request, server_id):
        try:
            server = resolve_server(server_id)
        except ServerResolutionError as exc:
            return _error(exc)
        _audit(request, "mcp.servers.read", server)
        return Response(ServerReadSerializer(server).data)


class ServerMetricsView(ControlAPIView):
    permission_classes = [require_scope("metrics:read")]
    def get(self, request, server_id):
        try:
            server = resolve_server(server_id)
        except ServerResolutionError as exc:
            return _error(exc)
        if server.last_seen_at is None:
            return Response({"error": "metrics_unavailable", "message": "No metrics snapshot is available."}, status=409)
        if server.status == "offline":
            return Response({
                "error": "server_offline",
                "message": "Server has not reported recently.",
                "last_seen_at": server.last_seen_at,
            }, status=409)
        _audit(request, "mcp.metrics.read", server)
        return Response(MetricsReadSerializer(server).data)


class ServiceListView(ControlAPIView):
    permission_classes = [require_scope("services:read")]
    def get(self, request, server_id):
        try:
            server = resolve_server(server_id)
        except ServerResolutionError as exc:
            return _error(exc)
        qs = server.services.all()
        state = request.query_params.get("status")
        if state:
            qs = qs.filter(active_state=state)
        _audit(request, "mcp.services.read", server, {"count": qs.count(), "status": state} if state else {"count": qs.count()})
        return Response({"items": ServiceReadSerializer(qs, many=True).data})


class ServiceDetailView(ControlAPIView):
    permission_classes = [require_scope("services:read")]
    def get(self, request, server_id, unit_name):
        try:
            server = resolve_server(server_id)
        except ServerResolutionError as exc:
            return _error(exc)
        service = server.services.filter(unit_name=unit_name).first()
        if service is None:
            return Response({"error": "service_not_found", "message": "The requested service does not exist."}, status=404)
        _audit(request, "mcp.services.read", server, {"unit_name": unit_name})
        return Response(ServiceReadSerializer(service).data)


class AuditListView(ControlAPIView):
    permission_classes = [require_scope("audit:read")]
    def get(self, request):
        try:
            limit = max(1, min(int(request.query_params.get("limit", "20")), 100))
        except ValueError:
            return Response({"error": "invalid_request", "message": "limit must be an integer."}, status=400)
        qs = AuditEvent.objects.all()
        server_id = request.query_params.get("server_id")
        server = None
        if server_id:
            try:
                server = resolve_server(server_id)
            except ServerResolutionError as exc:
                return _error(exc)
            qs = qs.filter(target_type="server", target_id=str(server.public_id))
        items = list(qs[:limit])
        _audit(request, "mcp.audit.read", server, {"limit": limit, "count": len(items)})
        return Response({"items": AuditReadSerializer(items, many=True).data})
```

`ServiceListView` accepts only an exact `active_state` value; it does not interpret shell/glob syntax. No view reads or logs request headers.

Map `DefaultServerNotConfigured` to HTTP 409 body:

```json
{"error":"default_server_not_configured","message":"Default server is not configured."}
```

Map unknown UUID to HTTP 404:

```json
{"error":"server_not_found","message":"The requested server does not exist."}
```

- [ ] **Step 7: Add `create_service_principal` command that returns the MCP token once**

```python
# apps/api/control/management/commands/create_service_principal.py
from django.core.management.base import BaseCommand, CommandError
from control.models import ServiceCredential, ServicePrincipal
from control.security import issue_secret

READ_SCOPES = ["servers:read", "metrics:read", "services:read", "audit:read"]


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("name")

    def handle(self, *args, **options):
        principal, created = ServicePrincipal.objects.get_or_create(
            name=options["name"], defaults={"scopes": READ_SCOPES}
        )
        if not created and principal.credentials.filter(revoked_at__isnull=True).exists():
            raise CommandError("principal already has an active credential")
        principal.scopes = READ_SCOPES
        principal.is_active = True
        principal.save(update_fields=["scopes", "is_active"])
        issued = issue_secret("service")
        ServiceCredential.objects.create(
            principal=principal, token_prefix=issued.prefix, token_hash=issued.digest
        )
        self.stdout.write(issued.cleartext)
```

- [ ] **Step 8: Wire routes and run all Django tests**

Add before the legacy include:

```python
path("api/control/v1/", include("control.control_urls")),
```

Run:

```bash
cd apps/api
python manage.py test control.tests -v 2
python manage.py check
```

Expected: PASS. Manually inspect serializer field lists to confirm there is no `agent_url`, token hash, token prefix, credential relation, or secret field.

- [ ] **Step 9: Commit Task 4**

```bash
git add apps/api/control apps/api/platform_api/urls.py
git commit -m "feat: add scoped read control API"
```

---

### Task 5: Convert the host agent to optional outbound enrollment + heartbeat mode

**Files:**
- Modify: `agent/pyproject.toml`
- Modify: `agent/digitalafarin_agent/config.py`
- Create: `agent/digitalafarin_agent/identity.py`
- Create: `agent/digitalafarin_agent/control_plane.py`
- Create: `agent/digitalafarin_agent/heartbeat.py`
- Modify: `agent/digitalafarin_agent/security.py`
- Modify: `agent/digitalafarin_agent/main.py`
- Create: `agent/tests/test_identity.py`
- Create: `agent/tests/test_control_plane.py`
- Create: `agent/tests/test_heartbeat.py`

**Interfaces:**
- Consumes: Django `/api/agent/v1/enroll` and `/heartbeat` contracts from Task 3, existing `collect_metrics()` and `list_services()`.
- Produces: `AgentIdentityStore`, `AgentControlPlaneClient`, `build_heartbeat_payload()`, `HeartbeatRunner.run_forever()`. Legacy inbound endpoints remain available when `PLATFORM_AGENT_TOKEN` is configured.

- [ ] **Step 1: Add agent test dependencies and failing identity tests**

Update dependencies:

```toml
# agent/pyproject.toml
"httpx>=0.28,<1",

[project.optional-dependencies]
dev = ["pytest>=8,<9", "pytest-asyncio>=0.25,<1"]
```

```python
# agent/tests/test_identity.py
from pathlib import Path
from digitalafarin_agent.identity import AgentIdentityStore


def test_token_file_is_written_and_read_with_owner_only_mode(tmp_path: Path):
    path = tmp_path / "agent.token"
    store = AgentIdentityStore(path)
    store.write("da_agent_prefix.secret")
    assert store.read() == "da_agent_prefix.secret"
    assert (path.stat().st_mode & 0o777) == 0o600
```

- [ ] **Step 2: Run test and verify missing identity module fails**

```bash
cd agent
python -m pip install -e '.[dev]'
pytest -q tests/test_identity.py
```

Expected: FAIL on missing module.

- [ ] **Step 3: Implement secure identity-file storage**

```python
# agent/digitalafarin_agent/identity.py
import os
from pathlib import Path


class AgentIdentityStore:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> str | None:
        if not self.path.exists():
            return None
        return self.path.read_text(encoding="utf-8").strip() or None

    def write(self, token: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, (token.strip() + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        os.chmod(self.path, 0o600)
```

- [ ] **Step 4: Expand config without requiring the legacy inbound token**

```python
# agent/digitalafarin_agent/config.py
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    platform_agent_token: str | None = None  # legacy local pull auth
    platform_control_url: str | None = None
    platform_enrollment_token: str | None = None
    agent_token_path: Path = Path("/var/lib/digitalafarin-agent/agent.token")
    agent_heartbeat_interval_seconds: int = 15
    agent_name: str = "DigitalAfarin VPS"
    agent_service_prefixes: str = "digitalafarin-"
```

Replace `agent/digitalafarin_agent/security.py` with a fail-closed dependency:

```python
import secrets
from fastapi import Header, HTTPException, status
from digitalafarin_agent.config import get_settings


def require_agent_token(authorization: str | None = Header(default=None)) -> None:
    expected = get_settings().platform_agent_token
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Legacy agent API disabled")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    supplied = authorization[7:].strip()
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
```

- [ ] **Step 5: Write failing control-plane client tests using `httpx.MockTransport`**

```python
# agent/tests/test_control_plane.py
import httpx
import pytest
from digitalafarin_agent.control_plane import AgentControlPlaneClient


@pytest.mark.asyncio
async def test_enroll_uses_enrollment_bearer_and_returns_agent_token():
    async def handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer enroll-token"
        return httpx.Response(201, json={"server_id": "11111111-1111-1111-1111-111111111111", "agent_token": "da_agent_p.s"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AgentControlPlaneClient("https://control.example", http=http)
    result = await client.enroll("enroll-token", {"name": "VPS", "hostname": "host", "agent_version": "0.2.0", "capabilities": []})
    assert result.agent_token == "da_agent_p.s"
    await http.aclose()
```

- [ ] **Step 6: Implement async agent client with sanitized errors**

```python
# agent/digitalafarin_agent/control_plane.py
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
            return EnrollmentResponse(server_id=data["server_id"], agent_token=data["agent_token"])
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

    async def close(self):
        if self._owns_http:
            await self.http.aclose()
```

- [ ] **Step 7: Write heartbeat payload/runner tests before implementation**

```python
# agent/tests/test_heartbeat.py
from digitalafarin_agent.heartbeat import build_heartbeat_payload


def test_payload_contains_only_collected_metrics_and_allowlisted_services(monkeypatch):
    monkeypatch.setattr("digitalafarin_agent.heartbeat.collect_metrics", lambda: {
        "cpu_percent": 10.0, "memory_percent": 20.0, "disk_percent": 30.0, "uptime_seconds": 40
    })
    monkeypatch.setattr("digitalafarin_agent.heartbeat.list_services", lambda: [{
        "unit_name": "digitalafarin-platform-api.service", "description": "API", "load_state": "loaded", "active_state": "active", "sub_state": "running"
    }])
    payload = build_heartbeat_payload("host", "0.2.0")
    assert payload["hostname"] == "host"
    assert payload["services"][0]["unit_name"] == "digitalafarin-platform-api.service"
    assert "token" not in str(payload).lower()
```

- [ ] **Step 8: Implement payload builder and runner; start it via FastAPI lifespan only when configured**

```python
# agent/digitalafarin_agent/heartbeat.py
import asyncio
import socket
from digitalafarin_agent import __version__
from digitalafarin_agent.metrics import collect_metrics
from digitalafarin_agent.systemd import list_services


def build_heartbeat_payload(hostname: str | None = None, agent_version: str = __version__) -> dict:
    return {
        "agent_version": agent_version,
        "hostname": hostname or socket.gethostname(),
        "capabilities": ["metrics", "systemd_inventory"],
        "metrics": collect_metrics(),
        "services": list_services(),
    }


class HeartbeatRunner:
    def __init__(self, *, client, identity_store, enrollment_token: str | None,
                 agent_name: str, interval_seconds: int):
        self.client = client
        self.identity_store = identity_store
        self.enrollment_token = enrollment_token
        self.agent_name = agent_name
        self.interval_seconds = interval_seconds

    async def ensure_identity(self) -> str:
        token = self.identity_store.read()
        if token:
            return token
        if not self.enrollment_token:
            raise RuntimeError("agent is not enrolled and no enrollment token is configured")
        payload = build_heartbeat_payload()
        result = await self.client.enroll(self.enrollment_token, {
            "name": self.agent_name,
            "hostname": payload["hostname"],
            "agent_version": payload["agent_version"],
            "capabilities": payload["capabilities"],
        })
        self.identity_store.write(result.agent_token)
        return result.agent_token

    async def run_forever(self):
        token = await self.ensure_identity()
        while True:
            try:
                await self.client.heartbeat(token, build_heartbeat_payload())
            except Exception as exc:
                # Log only the exception class; never serialize HTTP headers or bearer values.
                import logging
                logging.getLogger(__name__).warning("heartbeat failed: %s", type(exc).__name__)
            await asyncio.sleep(self.interval_seconds)
```

Wire it into FastAPI with an explicit lifespan:

```python
# agent/digitalafarin_agent/main.py
import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import Depends, FastAPI

from . import __version__
from .config import get_settings
from .control_plane import AgentControlPlaneClient
from .heartbeat import HeartbeatRunner
from .identity import AgentIdentityStore
from .metrics import collect_metrics
from .security import require_agent_token
from .systemd import list_services


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    task = None
    client = None
    if settings.platform_control_url:
        client = AgentControlPlaneClient(settings.platform_control_url)
        runner = HeartbeatRunner(
            client=client,
            identity_store=AgentIdentityStore(settings.agent_token_path),
            enrollment_token=settings.platform_enrollment_token,
            agent_name=settings.agent_name,
            interval_seconds=settings.agent_heartbeat_interval_seconds,
        )
        task = asyncio.create_task(runner.run_forever())
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if client:
            await client.close()


app = FastAPI(title="DigitalAfarin Host Agent", version=__version__, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "digitalafarin-host-agent", "version": __version__}

@app.get("/v1/metrics", dependencies=[Depends(require_agent_token)])
def metrics() -> dict:
    return collect_metrics()

@app.get("/v1/services", dependencies=[Depends(require_agent_token)])
def services() -> dict:
    return {"items": list_services()}
```

- [ ] **Step 9: Run complete agent tests and static secret/shell scan**

```bash
cd agent
pytest -q
cd ..
grep -R "shell=True\|os.system\|subprocess.*shell" -n agent || true
grep -R "Authorization.*print\|agent_token.*print" -n agent || true
```

Expected: pytest PASS; scans return no executable arbitrary-shell pattern and no obvious token logging.

- [ ] **Step 10: Commit Task 5**

```bash
git add agent
git commit -m "feat: add outbound agent heartbeat mode"
```

---

### Task 6: Build the read-only MCP server against the Django control API

**Files:**
- Create: `mcp/pyproject.toml`
- Create: `mcp/digitalafarin_vps_mcp/__init__.py`
- Create: `mcp/digitalafarin_vps_mcp/config.py`
- Create: `mcp/digitalafarin_vps_mcp/errors.py`
- Create: `mcp/digitalafarin_vps_mcp/control_plane.py`
- Create: `mcp/digitalafarin_vps_mcp/server.py`
- Create: `mcp/tests/test_control_plane.py`
- Create: `mcp/tests/test_server.py`

**Interfaces:**
- Consumes: Task 4 control API and service credential.
- Produces: localhost-only `MCPServer` with exactly six tools: `vps_list_servers`, `vps_get_server`, `vps_get_metrics`, `vps_list_services`, `vps_get_service`, `vps_get_recent_audit_events`.

- [ ] **Step 1: Create MCP package with current stable v2 dependency line**

```toml
# mcp/pyproject.toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "digitalafarin-vps-mcp"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "mcp>=2,<3",
  "httpx>=0.28,<1",
  "pydantic-settings>=2.7,<3",
]

[project.optional-dependencies]
dev = ["pytest>=8,<9", "pytest-asyncio>=0.25,<1"]

[tool.setuptools.packages.find]
where = ["."]
include = ["digitalafarin_vps_mcp*"]
```

- [ ] **Step 2: Write failing client error-normalization tests**

```python
# mcp/tests/test_control_plane.py
import httpx
import pytest
from digitalafarin_vps_mcp.control_plane import ControlPlaneClient
from digitalafarin_vps_mcp.errors import MCPDomainError


@pytest.mark.asyncio
async def test_404_is_normalized_without_raw_response_body():
    async def handler(request: httpx.Request):
        return httpx.Response(404, json={"error": "server_not_found", "message": "The requested server does not exist."})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ControlPlaneClient("http://control", "service-secret", http=http)
    with pytest.raises(MCPDomainError) as exc:
        await client.get_server("bad")
    assert exc.value.code == "server_not_found"
    assert "traceback" not in str(exc.value).lower()
    await http.aclose()
```

- [ ] **Step 3: Implement config, sanitized error type, and async REST client**

```python
# mcp/digitalafarin_vps_mcp/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    control_plane_url: str = "http://127.0.0.1:8000"
    control_plane_token: str
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 3060
    mcp_path: str = "/mcp"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# mcp/digitalafarin_vps_mcp/errors.py
class MCPDomainError(RuntimeError):
    def __init__(self, code: str, message: str, data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}

    def as_dict(self) -> dict:
        return {"error": self.code, "message": self.message, **self.data}
```

Implement the client with explicit status normalization and no raw response-text propagation:

```python
# mcp/digitalafarin_vps_mcp/control_plane.py
import re
from urllib.parse import quote
import httpx
from digitalafarin_vps_mcp.errors import MCPDomainError

_SERVICE_RE = re.compile(r"^[A-Za-z0-9_.@:-]+$")


class ControlPlaneClient:
    def __init__(self, base_url: str, token: str, http: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.http = http or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http is None

    async def _get(self, path: str, params: dict | None = None) -> dict:
        try:
            response = await self.http.get(
                f"{self.base_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self.token}"},
            )
        except httpx.HTTPError as exc:
            raise MCPDomainError("control_plane_unavailable", "Control plane is unavailable.") from exc
        if response.status_code >= 500:
            raise MCPDomainError("control_plane_unavailable", "Control plane is unavailable.")
        if response.status_code < 400:
            return response.json()
        try:
            body = response.json()
        except ValueError:
            body = {}
        code = body.get("error")
        message = body.get("message")
        if response.status_code == 400:
            raise MCPDomainError("invalid_request", message or "The request is invalid.")
        if response.status_code == 403:
            raise MCPDomainError("forbidden", "This MCP identity cannot perform this operation.")
        if response.status_code == 404:
            raise MCPDomainError(code if code in {"server_not_found", "service_not_found"} else "server_not_found", message or "The requested resource does not exist.")
        if response.status_code == 409:
            allowed = {"default_server_not_configured", "server_offline", "metrics_unavailable"}
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
        raise MCPDomainError("control_plane_unavailable", "Control plane request failed.")

    @staticmethod
    def _server_id(server_id: str | None) -> str:
        return server_id or "default"

    async def list_servers(self) -> dict:
        return await self._get("/api/control/v1/servers/")

    async def get_server(self, server_id: str | None) -> dict:
        return await self._get(f"/api/control/v1/servers/{self._server_id(server_id)}/")

    async def get_metrics(self, server_id: str | None) -> dict:
        return await self._get(f"/api/control/v1/servers/{self._server_id(server_id)}/metrics/")

    async def list_services(self, server_id: str | None, status: str | None) -> dict:
        params = {"status": status} if status else None
        return await self._get(f"/api/control/v1/servers/{self._server_id(server_id)}/services/", params=params)

    async def get_service(self, service_name: str, server_id: str | None) -> dict:
        if not _SERVICE_RE.fullmatch(service_name):
            raise MCPDomainError("invalid_request", "service_name must be an exact systemd unit name.")
        safe_name = quote(service_name, safe="")
        return await self._get(f"/api/control/v1/servers/{self._server_id(server_id)}/services/{safe_name}/")

    async def get_audit(self, server_id: str | None, limit: int) -> dict:
        params = {"limit": max(1, min(limit, 100))}
        if server_id:
            params["server_id"] = server_id
        return await self._get("/api/control/v1/audit/", params=params)

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()
```

`server_id=None` maps to path identifier `default`. `service_name` is validated before making HTTP requests.

- [ ] **Step 4: Write in-memory MCP tool tests before server implementation**

```python
# mcp/tests/test_server.py
import pytest
from mcp import Client
from digitalafarin_vps_mcp.server import create_mcp


class FakeControlPlane:
    async def list_servers(self):
        return {"items": [{"id": "11111111-1111-1111-1111-111111111111", "name": "Primary", "status": "online"}]}
    async def get_server(self, server_id):
        return {"id": "11111111-1111-1111-1111-111111111111", "name": "Primary", "status": "online"}
    async def get_metrics(self, server_id):
        return {"id": "11111111-1111-1111-1111-111111111111", "cpu_percent": 10.0, "stale": False}
    async def list_services(self, server_id, status):
        return {"items": []}
    async def get_service(self, service_name, server_id):
        return {"unit_name": service_name, "active_state": "active"}
    async def get_audit(self, server_id, limit):
        return {"items": []}


@pytest.mark.asyncio
async def test_server_discovers_exactly_six_read_only_tools():
    mcp = create_mcp(FakeControlPlane())
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.list_tools()
        names = {tool.name for tool in result.tools}
    assert names == {
        "vps_list_servers", "vps_get_server", "vps_get_metrics",
        "vps_list_services", "vps_get_service", "vps_get_recent_audit_events",
    }
```

- [ ] **Step 5: Implement `MCPServer` factory and six thin tools**

```python
# mcp/digitalafarin_vps_mcp/server.py
from mcp.server import MCPServer
from digitalafarin_vps_mcp.control_plane import ControlPlaneClient
from digitalafarin_vps_mcp.errors import MCPDomainError
from digitalafarin_vps_mcp.config import get_settings


def create_mcp(control_plane=None) -> MCPServer:
    if control_plane is None:
        settings = get_settings()
        client = ControlPlaneClient(settings.control_plane_url, settings.control_plane_token)
    else:
        client = control_plane
    mcp = MCPServer(
        "DigitalAfarin VPS",
        instructions="Read-only VPS inventory and health. Never claim to restart, deploy, or mutate a server.",
    )

    async def safe(call):
        try:
            return await call
        except MCPDomainError as exc:
            return exc.as_dict()

    @mcp.tool()
    async def vps_list_servers() -> dict:
        """List registered VPS hosts and freshness state."""
        return await safe(client.list_servers())

    @mcp.tool()
    async def vps_get_server(server_id: str | None = None) -> dict:
        """Read one VPS by UUID; omit server_id to use the configured default server."""
        return await safe(client.get_server(server_id))

    @mcp.tool()
    async def vps_get_metrics(server_id: str | None = None) -> dict:
        """Read CPU, RAM, disk, uptime, collection time, and freshness for one VPS."""
        return await safe(client.get_metrics(server_id))

    @mcp.tool()
    async def vps_list_services(server_id: str | None = None, status: str | None = None) -> dict:
        """List allow-listed systemd service snapshots for one VPS."""
        return await safe(client.list_services(server_id, status))

    @mcp.tool()
    async def vps_get_service(service_name: str, server_id: str | None = None) -> dict:
        """Read one exact allow-listed systemd unit snapshot; no fuzzy or shell input."""
        return await safe(client.get_service(service_name, server_id))

    @mcp.tool()
    async def vps_get_recent_audit_events(server_id: str | None = None, limit: int = 20) -> dict:
        """Read recent sanitized control-plane audit events; limit is clamped server-side."""
        return await safe(client.get_audit(server_id, limit))

    return mcp


if __name__ == "__main__":
    settings = get_settings()
    create_mcp().run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path=settings.mcp_path,
    )
```

Note: tool registration is deliberately explicit. There must be no tool named `shell`, `command`, `exec`, `restart`, `deploy`, `stop`, `start`, `write`, or equivalent.

- [ ] **Step 6: Run MCP tests and verify real Streamable HTTP binds to loopback**

```bash
cd mcp
python -m pip install -e '.[dev]'
pytest -q
CONTROL_PLANE_TOKEN=dummy timeout 3 python -m digitalafarin_vps_mcp.server || test $? -eq 124
```

In a second local shell during manual verification (with a real development service token), use the v2 client:

```python
import asyncio
from mcp import Client

async def main():
    async with Client("http://127.0.0.1:3060/mcp") as client:
        tools = await client.list_tools()
        print([tool.name for tool in tools.tools])

asyncio.run(main())
```

Expected: exactly six tool names; no public bind such as `0.0.0.0:3060`.

- [ ] **Step 7: Commit Task 6**

```bash
git add mcp
git commit -m "feat: add read-only VPS MCP server"
```

---

### Task 7: Add deployment units, environment contract, and end-to-end acceptance runbook

**Files:**
- Modify: `.env.example`
- Rename/modify: `infra/systemd/digitalafarin-agent.service` -> `infra/systemd/digitalafarin-platform-agent.service`
- Rename/modify: `infra/systemd/digitalafarin-api.service` -> `infra/systemd/digitalafarin-platform-api.service`
- Rename/modify: `infra/systemd/digitalafarin-web.service` -> `infra/systemd/digitalafarin-platform-web.service`
- Create: `infra/systemd/digitalafarin-platform-mcp.service`
- Create: `infra/systemd/digitalafarin-platform-mcp-tunnel.service`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: agent/control API/MCP services from Tasks 1-6 and the user-created Secure MCP Tunnel profile `digitalafarin-vps`.
- Produces: reproducible production service configuration and a concrete acceptance sequence from enrollment through ChatGPT tool invocation.

- [ ] **Step 1: Extend `.env.example` with names only and safe dummy values**

```dotenv
# Existing legacy compatibility
PLATFORM_API_TOKEN=replace-me
PLATFORM_AGENT_TOKEN=replace-me

# Agent outbound mode
PLATFORM_CONTROL_URL=https://panel.example.com
PLATFORM_ENROLLMENT_TOKEN=one-time-value-only-during-first-enrollment
AGENT_TOKEN_PATH=/var/lib/digitalafarin-agent/agent.token
AGENT_HEARTBEAT_INTERVAL_SECONDS=15
AGENT_NAME=DigitalAfarin-Primary
AGENT_SERVICE_PREFIXES=digitalafarin-,oily-,khoshvisa-

# MCP -> Django
CONTROL_PLANE_URL=http://127.0.0.1:8000
CONTROL_PLANE_TOKEN=replace-me-with-service-principal-token
MCP_HOST=127.0.0.1
MCP_PORT=3060
MCP_PATH=/mcp
```

Do not put real production tokens into this file or Git.

- [ ] **Step 2: Canonicalize existing unit names and update agent unit for persistent identity state**

Rename the committed units to match the approved deployment names:

```bash
git mv infra/systemd/digitalafarin-api.service infra/systemd/digitalafarin-platform-api.service
git mv infra/systemd/digitalafarin-web.service infra/systemd/digitalafarin-platform-web.service
git mv infra/systemd/digitalafarin-agent.service infra/systemd/digitalafarin-platform-agent.service
```

In `digitalafarin-platform-web.service`, change `After=digitalafarin-api.service` to `After=digitalafarin-platform-api.service`. Required agent service properties:

```ini
[Service]
User=digitalafarin-agent
Group=digitalafarin-agent
WorkingDirectory=/opt/digitalafarin-platform/agent
EnvironmentFile=/etc/digitalafarin-platform/agent.env
StateDirectory=digitalafarin-agent
StateDirectoryMode=0700
ExecStart=/opt/digitalafarin-platform/agent/.venv/bin/uvicorn digitalafarin_agent.main:app --host 127.0.0.1 --port 9743
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/digitalafarin-agent
```

`AGENT_TOKEN_PATH` in `/etc/digitalafarin-platform/agent.env` must be `/var/lib/digitalafarin-agent/agent.token`. The first successful enrollment writes it `0600`; immediately remove `PLATFORM_ENROLLMENT_TOKEN` from `agent.env` and restart the service.

- [ ] **Step 3: Add localhost-only MCP systemd service**

```ini
# infra/systemd/digitalafarin-platform-mcp.service
[Unit]
Description=DigitalAfarin VPS MCP
After=network-online.target digitalafarin-platform-api.service
Wants=network-online.target

[Service]
Type=simple
User=digitalafarin-mcp
Group=digitalafarin-mcp
WorkingDirectory=/opt/digitalafarin-platform/mcp
EnvironmentFile=/etc/digitalafarin-platform/mcp.env
ExecStart=/opt/digitalafarin-platform/mcp/.venv/bin/python -m digitalafarin_vps_mcp.server
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Add Secure MCP Tunnel systemd service using the already-created profile**

```ini
# infra/systemd/digitalafarin-platform-mcp-tunnel.service
[Unit]
Description=DigitalAfarin VPS MCP Secure Tunnel
After=network-online.target digitalafarin-platform-mcp.service
Wants=network-online.target

[Service]
Type=simple
User=digitalafarin-mcp
Group=digitalafarin-mcp
ExecStart=/usr/local/bin/tunnel-client run --profile digitalafarin-vps
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

If `tunnel-client` is installed at another actual path on the VPS, determine it with `command -v tunnel-client` during deployment and update only `ExecStart`; do not guess a path in production.

- [ ] **Step 5: Document exact first-server enrollment and MCP principal bootstrap**

Add this runbook to `README.md`:

```bash
# On control-plane host
cd /opt/digitalafarin-platform/apps/api
source .venv/bin/activate
python manage.py migrate
python manage.py create_enrollment_token --minutes 15 --created-by rahi
# Copy the one-time output into /etc/digitalafarin-platform/agent.env as PLATFORM_ENROLLMENT_TOKEN.

sudo systemctl restart digitalafarin-platform-agent
sudo journalctl -u digitalafarin-platform-agent -n 100 --no-pager
# After successful enrollment:
sudo sed -i '/^PLATFORM_ENROLLMENT_TOKEN=/d' /etc/digitalafarin-platform/agent.env
sudo systemctl restart digitalafarin-platform-agent

# Make this server the default using Django admin or shell, by UUID-selected row:
python manage.py shell -c 'from control.models import Server; s=Server.objects.order_by("created_at").first(); Server.objects.update(is_default=False); s.is_default=True; s.save(update_fields=["is_default"]); print(s.public_id)'

# Create MCP read principal; copy the one-time output to mcp.env as CONTROL_PLANE_TOKEN.
python manage.py create_service_principal chatgpt-vps-mcp

sudo systemctl restart digitalafarin-platform-mcp
sudo systemctl restart digitalafarin-platform-mcp-tunnel
```

The runbook must explicitly say: never paste the printed enrollment/agent/service credential into ChatGPT, issue trackers, Git commits, or logs.

- [ ] **Step 6: Add local and production acceptance checks**

Document and execute locally where applicable:

```bash
# Django
cd apps/api
python manage.py test control.tests -v 2
python manage.py check

# Agent
cd ../../agent
pytest -q

# MCP
cd ../mcp
pytest -q

# Repository safety
cd ..
git diff --check
grep -R "shell=True\|os.system\|subprocess.*shell" -n apps agent mcp || true
git grep -nE 'da_(agent|service|enroll)_[A-Za-z0-9]{8,}\.[A-Za-z0-9_-]{40,}' -- ':!*.md' || true
```

Production VPS checks after deployment:

```bash
sudo systemctl is-active digitalafarin-platform-api digitalafarin-platform-web digitalafarin-platform-agent digitalafarin-platform-mcp digitalafarin-platform-mcp-tunnel
curl -fsS http://127.0.0.1:8000/health/
ss -ltnp | grep ':3060'  # must show loopback, not 0.0.0.0/::
tunnel-client doctor --profile digitalafarin-vps --explain
```

Then use the ChatGPT connector to invoke, in order:

```text
vps_list_servers()
vps_get_server()
vps_get_metrics()
vps_list_services()
```

Acceptance requires real primary-VPS values, a fresh timestamp/`stale=false`, and no credentials in any tool output.

- [ ] **Step 7: Update architecture docs with Stage A-D deprecation status**

Record:

```text
Stage A complete: additive UUID identity, credentials, agent/control APIs.
Stage B complete: primary agent outbound heartbeat proven.
Stage C complete: MCP read path + Secure MCP Tunnel proven from ChatGPT.
Stage D deferred: remove legacy agent_url/manual sync/shared agent token only after an explicit cleanup change.
```

Do not delete the legacy path in this task.

- [ ] **Step 8: Run repository verification and commit Task 7**

```bash
git diff --check
git status --short
git add .env.example infra README.md docs/ARCHITECTURE.md
git commit -m "docs: add VPS MCP deployment runbook"
```

---

## Final Milestone Verification

Run all automated suites from the repository root:

```bash
cd apps/api && python manage.py test control.tests -v 2 && python manage.py check
cd ../../agent && pytest -q
cd ../mcp && pytest -q
cd .. && git diff --check
```

Then verify production end-to-end:

```text
Agent on primary VPS
  -> authenticated outbound heartbeat
  -> Django latest snapshots
  -> scoped MCP service-principal REST read
  -> 127.0.0.1:3060/mcp
  -> Secure MCP Tunnel
  -> ChatGPT read-only tools
```

The milestone is complete only when ChatGPT can list the actual primary VPS, report real CPU/RAM/disk/uptime, and list actual allow-listed systemd services without manual SSH and without exposing any secret.
