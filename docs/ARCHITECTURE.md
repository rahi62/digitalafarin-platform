# Architecture decision record — multi-server read-only VPS MCP

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

A small process installed on every VPS. It collects metrics and allow-listed systemd inventory, enrolls once with an expiring credential, persists its own independent agent credential, and sends periodic outbound heartbeats. Its legacy loopback read API remains temporarily for migration compatibility.

### DigitalAfarin VPS MCP

Read-only MCP Python SDK v2 service listening on `127.0.0.1:3060/mcp`. It authenticates to Django with a dedicated service principal scoped to:

```text
servers:read
metrics:read
services:read
audit:read
```

Its six approved tools are:

```text
vps_list_servers
vps_get_server
vps_get_metrics
vps_list_services
vps_get_service
vps_get_recent_audit_events
```

There is no generic shell tool and no write-capable VPS tool in v1.

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

### Stage B — pending production acceptance

Primary VPS Agent must be deployed and prove sustained authenticated outbound heartbeats with fresh real metrics/services. Local Agent tests alone do not mark this stage complete.

### Stage C — pending production acceptance

The MCP must be deployed on loopback, use the production Django API listener at `127.0.0.1:9750`, the existing `digitalafarin-vps` Secure MCP Tunnel must pass `doctor` under the MCP service account, and ChatGPT must return real primary-VPS data through the six read-only tools. Local source tests alone do not mark this stage complete.

### Stage D — deferred cleanup

Only after explicit production acceptance, remove the legacy shared agent token, `agent_url` pull path and manual sync flow in a separate reviewed change.

## Future typed operation interface

State-changing work will use a queued operation model rather than remote shell execution:

```text
queued -> claimed -> running -> succeeded | failed
```

Approved future operation kinds may include:

```text
service.restart
service.start
service.stop
deployment.deploy
deployment.rollback
backup.create
nginx.reload
```

There will be no `shell.execute` operation.
