# Architecture decision record — outbound control plane and migration deployment engine

## Goal

Replace recurring SSH-only operational inspection with a safe internal control plane that supports multiple VPS hosts without exposing inbound Agent ports or giving ChatGPT arbitrary server execution.

## Data flow

```text
ChatGPT
  -> OpenAI Secure MCP Tunnel
  -> DigitalAfarin VPS MCP (127.0.0.1:3060/mcp)
  -> Django scoped Control API
  -> PostgreSQL snapshots

Each VPS Host Agent
  -> authenticated outbound HTTPS enrollment/heartbeat
  -> Django Agent API
```

MCP is a client of Django only. It never contacts a Host Agent or PostgreSQL directly.

## Components

### Next.js Admin

Presentation layer. The current UI can temporarily use the legacy API while it is migrated to UUID-based Control API reads. Browser code never receives Agent or MCP service credentials.

### Django Control Plane

System of record for server identity, agent/service credentials, metrics, service snapshots and audit events. External server identity is a stable UUID; the legacy integer primary key remains internal during migration.

### Python Host Agent

A small process installed on every VPS. It collects metrics and allow-listed
systemd inventory, enrolls once with an expiring credential, persists its own
independent agent credential, and sends periodic outbound heartbeats. During the
same outbound loop it claims typed operations, reports `started`, executes a
fixed handler, and completes the operation. It exposes no inbound management
route. Its legacy loopback read API remains temporarily for migration
compatibility.

### DigitalAfarin VPS MCP

MCP Python SDK v2 service listening on `127.0.0.1:3060/mcp`. It authenticates to Django with a dedicated operator principal scoped to inventory reads and typed operations:

```text
servers:read
metrics:read
services:read
audit:read
operations:read
operations:create
logs:read
```

Its approved tools cover inventory, bounded service operations, secret-free
project/deployment reads, deploy/redeploy, and rollback:

```text
vps_list_servers
vps_get_server
vps_get_metrics
vps_list_services
vps_get_service
vps_get_recent_audit_events
vps_create_service_operation
vps_create_service_logs_operation
vps_list_operations
vps_get_operation
vps_list_projects
vps_get_project
vps_deploy_service
vps_get_deployment
vps_redeploy_deployment
vps_rollback_deployment
```

There is no generic shell, SQL, systemctl, filesystem, or configuration-text tool.

## Migration deployment extension

The deployment domain remains in Django: `Project` owns services and resources;
`Deployment` and immutable `DeploymentEvent` rows record intent and state; and
`Release` records exact Git commits and activation history. MCP and the Admin UI
use the same scoped Control API. Neither talks directly to PostgreSQL, systemd,
Nginx, the filesystem, or a host agent.

State-changing work is delivered through the outbound operation claim loop:

```text
Admin / MCP / GitHub webhook
  -> scoped Django Control API
  -> typed queued operation
  <- outbound Agent claim
  -> fixed handler / structured result
  -> redacted operation + deployment events
```

`SystemdExecutor` is the only active deployment executor. Runtime recipes select
fixed argument arrays for Node/Next.js or Python/Django; callers cannot provide
shell, SQL, systemctl arguments, Nginx text, filesystem roots, or package names.
The Agent prepares a fresh exact-commit checkout before touching `current`, writes
an execution-only mode-`0600` environment file, attaches platform-derived
persistent volumes, builds, atomically switches the symlink, restarts, and verifies
health. A failed post-activation health check restores the previous release and
verifies it without rebuilding.

Persistent and disposable roots are deliberately separate:

```text
/srv/digitalafarin/apps/<project>/<service>/releases  disposable immutable releases
/srv/digitalafarin/apps/<project>/<service>/current   atomic active symlink
/srv/digitalafarin/apps/<project>/<service>/shared    service-local persistent data
/srv/digitalafarin/volumes/<project>/<volume>         managed persistent volumes
/srv/digitalafarin/backups                             managed restore inputs
```

Five successful inactive releases are retained. Cleanup is restricted to the
service `releases/` directory, does not follow symlinks, and never touches shared
data, managed volumes, backups, or PostgreSQL data.

Deployment admission uses fresh heartbeat telemetry. Disk usage below 80% is
ready, `>=80%` is warning-but-allowed, and `>=90%`, missing, or stale telemetry
blocks creation before an operation is queued.

Deployment secrets are authenticated-encrypted under the versioned
`PLATFORM_SECRET_KEYS` key ring. The first key encrypts; all listed keys may
decrypt during rotation. Plaintext enters only write endpoints and authorized
execution context. API, UI, MCP, logs, operation results, and audit events expose
metadata or redacted values only.

## Identity and credential boundaries

- Enrollment credential: one-time, expiring, stored by Django as a digest and invalidated after use.
- Agent credential: unique per VPS, revocable independently, cleartext persisted only on that VPS with file mode `0600`; Django stores only its digest.
- MCP service credential: independent from every Agent credential and limited to read scopes.
- ChatGPT/tool responses: never contain any of these credentials.

A compromised secondary VPS therefore does not receive credentials for the primary VPS or for MCP.

## Freshness model

Agents target a 15-second heartbeat interval.

```text
age <= 45 seconds   -> online
45 < age <= 120     -> stale
age > 120 seconds   -> offline
no heartbeat        -> offline
```

Server status is derived from `last_seen_at`; it is not stored as a second source of truth.

## Security rules

1. No `shell=True`.
2. No `os.system` or free-form command strings from Browser/API/MCP.
3. Secondary VPS Agents require no inbound public port.
4. Service discovery is prefix allow-listed.
5. Browser and ChatGPT never receive Agent credentials.
6. MCP binds to loopback and is reachable from ChatGPT only through the Secure MCP Tunnel.
7. Privileged actions are not implemented until typed operations, RBAC, audit and approval boundaries exist.
8. Future Nginx/deploy writes must use validate-before-switch semantics.
9. Future rollback must be a first-class typed operation, not an ad-hoc script.

## Migration / deprecation stages

### Stage A — implementation complete locally

Additive UUID identity, enrollment/agent credentials, outbound Agent API, scoped Control API and MCP source are implemented while legacy fields/routes stay intact.

### Stage B — migration deployment implementation complete locally

Bootstrap, encrypted resources, managed volumes and databases, immutable release
deployment, health verification, rollback, domains, migration UI/MCP, and the
disposable 18-check acceptance fixture are implemented. Production use remains
subject to the checks in `docs/migration-runbook.md`.

### Stage C — production acceptance

The API, Web, Agent, and MCP must be deployed from the same final `main` commit.
Listeners remain loopback-only, Nginx and systemd validation must pass, the existing
`digitalafarin-vps` Secure MCP Tunnel must pass `doctor` under its runtime
environment, and only non-destructive production acceptance is permitted unless a
specific mutation has been separately demonstrated safe. Local tests alone do not
mark this stage complete.

### Stage D — deferred cleanup

Only after explicit production acceptance, remove the legacy shared agent token, `agent_url` pull path and manual sync flow in a separate reviewed change.

## Typed operation interface

State-changing work uses a queued operation model rather than remote shell execution:

```text
queued -> claimed -> running -> succeeded | failed
```

Current operation kinds are:

```text
service.start
service.stop
service.restart
service.logs
volume.create
server.bootstrap
database.create
database.restore
deployment.deploy
deployment.rollback
domain.configure
domain.ssl
```

Claim leases recover operations abandoned before `running`; every accepted
transition writes an audit event in the same transaction. `service.logs` uses
fixed journal arguments, line/time/byte bounds, and redaction before persistence.
There is no `shell.execute` operation.
