# DigitalAfarin VPS MCP Multi-Server Design

Date: 2026-09-01
Status: Approved design, pending implementation plan
Project: DigitalAfarin Platform

## 1. Purpose

Extend the existing single-server, pull-based DigitalAfarin VPS Platform into a multi-server control plane that ChatGPT can read through a private MCP server connected with OpenAI Secure MCP Tunnel.

The first MCP milestone is intentionally read-only. From ChatGPT it must be possible to list registered VPS hosts, inspect a default or explicitly selected server, read current resource metrics, inspect allow-listed systemd services, and read recent audit events. No restart, stop, deploy, rollback, Nginx mutation, backup mutation, arbitrary shell execution, or other privileged write operation is included in this milestone.

## 2. Success Criteria

The milestone is complete when all of the following are true:

1. At least one VPS can enroll with a one-time enrollment credential.
2. Every enrolled VPS receives an independent agent identity and bearer credential.
3. Host agents make outbound authenticated HTTPS requests to the Django control plane; secondary VPS hosts expose no inbound agent port to the internet.
4. Agents send periodic heartbeats containing host metrics and allow-listed systemd service inventory.
5. Django persists server identity, freshness state, latest metrics, service snapshots, and audit events.
6. Multiple servers can coexist; the schema permits at most one active default server, and the production acceptance configuration must designate one default server.
7. The MCP server runs only on `127.0.0.1:3060` and exposes Streamable HTTP at `/mcp`.
8. OpenAI Secure MCP Tunnel connects ChatGPT to that local MCP endpoint without publishing it directly to the internet.
9. MCP tools read data only through the Django control-plane API; MCP does not query PostgreSQL or host agents directly.
10. ChatGPT can call the read-only MCP tools and receive structured, sanitized responses containing no secret tokens, raw tracebacks, or host-agent credentials.

## 3. Current State

The existing MVP has three components:

- Next.js admin in `apps/web`.
- Django control plane in `apps/api`.
- Python FastAPI host agent in `agent`.

The current data flow is single-server and pull-based:

```text
Next.js -> Django -> Host Agent on 127.0.0.1:9743
```

Django currently stores `Server.agent_url`, uses one process-wide `PLATFORM_AGENT_TOKEN`, and manually pulls metrics and service inventory through `AgentClient`.

That model is acceptable for the initial local MVP but is not suitable for multiple independent VPS hosts because it either requires inbound connectivity to every agent or a shared credential across hosts.

## 4. Target Architecture

The target data flow is:

```text
                                      +----------------------+
ChatGPT                               | DigitalAfarin VPS MCP |
   |                                  | 127.0.0.1:3060/mcp   |
   +---- OpenAI Secure MCP Tunnel --->+----------+-----------+
                                                 |
                                                 | authenticated internal API
                                                 v
                                      +----------------------+
                                      | Django Control Plane |
                                      | system of record     |
                                      +----------^-----------+
                                                 |
                                 outbound HTTPS  |
                     +---------------------------+---------------------------+
                     |                           |                           |
               +-----+------+              +-----+------+              +-----+------+
               | VPS Agent A |              | VPS Agent B |              | VPS Agent C |
               +------------+              +------------+              +------------+
```

### Architectural rule

Django remains the system of record and trust boundary. Host agents report to Django. MCP reads from Django. ChatGPT never talks directly to host agents.

## 5. Why Outbound Agents

Three approaches were considered:

1. Outbound agent heartbeat to Django.
2. Private overlay network such as WireGuard/Tailscale with Django pulling each agent.
3. Public agent HTTPS endpoints protected by mTLS.

The selected approach is outbound agent heartbeat because it minimizes exposed ports, isolates host credentials, works across unrelated datacenters, and keeps multi-server onboarding independent of network topology.

A private overlay network may be added later for other operational needs, but it is not required by this design.

## 6. Server Model

The `Server` model evolves from the current single-server record into a stable multi-server identity.

Required fields:

```text
id                UUID
name              string
hostname          string
is_default        boolean
is_active         boolean
status            derived property: online | stale | offline (not stored)
last_seen_at      datetime nullable
agent_version     string nullable
capabilities      JSON object
cpu_percent       float nullable
memory_percent    float nullable
disk_percent      float nullable
uptime_seconds    bigint nullable
created_at        datetime
updated_at        datetime
```

`agent_url` becomes legacy compatibility state and is deprecated after outbound heartbeat is proven in production.

### Default server invariant

At most one active server may have `is_default=true`. Application logic and a database constraint where practical must enforce that uniqueness invariant. Production acceptance additionally requires one active default server to be configured. If a tool omits `server_id`, the default active server is selected. If there is no default server, the MCP returns `default_server_not_configured` rather than guessing.

## 7. Agent Enrollment and Identity

### Enrollment

The control plane creates a one-time `EnrollmentToken` with:

```text
id
secret_hash
expires_at
used_at
created_by
created_at
```

The cleartext enrollment secret is displayed or returned only once. It is never stored in plaintext by Django.

An operator installs the agent on a VPS and supplies:

- control-plane base URL,
- one-time enrollment secret,
- local service allow-list configuration.

The agent calls:

```text
POST /api/agent/v1/enroll
```

with basic host identity and the one-time secret.

If valid and unused, Django creates or binds the `Server` record and returns a new server-specific bearer credential exactly once.

### Agent credential

Every server has an independent credential record:

```text
AgentCredential
- id
- server_id
- token_prefix
- token_hash
- created_at
- last_used_at
- revoked_at
```

The cleartext bearer token exists only on that VPS. Django stores only a one-way digest of a high-entropy 256-bit token. Compromise of one VPS credential must not authenticate as any other server.

Credential rotation and revocation are supported by the data model, even if the first UI for rotation is deferred.

## 8. Agent Heartbeat

After enrollment, the agent no longer needs an inbound HTTP API for normal control-plane synchronization.

Every 15 seconds it sends:

```text
POST /api/agent/v1/heartbeat
Authorization: Bearer <server-specific-agent-token>
```

Payload shape:

```json
{
  "agent_version": "x.y.z",
  "hostname": "server-1",
  "capabilities": ["metrics", "systemd_inventory"],
  "metrics": {
    "cpu_percent": 17.4,
    "memory_percent": 41.2,
    "disk_percent": 36.8,
    "uptime_seconds": 2848120
  },
  "services": [
    {
      "unit_name": "oily-backend.service",
      "description": "...",
      "load_state": "loaded",
      "active_state": "active",
      "sub_state": "running"
    }
  ]
}
```

Only services matching local configured allow-list prefixes are sent.

### Freshness

Default freshness thresholds:

```text
heartbeat interval: 15 seconds
stale:              last_seen age > 45 seconds
offline:            last_seen age > 120 seconds
```

Freshness is derived from timestamps rather than trusted from the agent.

MCP responses include `collected_at`, `age_seconds`, and `stale` where freshness matters.

## 9. Django Agent API

New agent-facing endpoints:

```text
POST /api/agent/v1/enroll
POST /api/agent/v1/heartbeat
```

Agent endpoints use dedicated authentication separate from the existing platform/browser authentication class.

Security requirements:

- HTTPS in production.
- Rate limiting at Nginx and/or application level.
- Constant-time token verification where applicable.
- Generic authentication failures that do not reveal whether a server/token exists.
- No raw Authorization headers in logs.
- No secret values in audit metadata.
- Enrollment token is one-time and expires.
- Revoked agent credentials fail immediately.

## 10. Service Snapshots

The existing `ServiceSnapshot` remains keyed by `(server, unit_name)` and is updated from heartbeat payloads.

The control plane stores the latest service state required by the UI and MCP. Historical time-series service telemetry is out of scope for this milestone.

A later observability milestone may add history without changing the MCP tool contracts.

## 11. MCP Service

A new top-level package is added:

```text
mcp/
  pyproject.toml
  digitalafarin_vps_mcp/
    __init__.py
    server.py
    config.py
    auth.py
    control_plane.py
    errors.py
    tools/
      __init__.py
      servers.py
      metrics.py
      services.py
      audit.py
  tests/
```

The implementation uses the official MCP Python SDK v2 stable release line and Streamable HTTP.

Runtime binding:

```text
host: 127.0.0.1
port: 3060
path: /mcp
```

The MCP endpoint is private. OpenAI Secure MCP Tunnel is the supported bridge from ChatGPT to the local endpoint.

## 12. MCP to Django Authentication

MCP receives its own control-plane service identity, independent of browser users and agents.

Logical principal:

```text
chatgpt-vps-mcp
```

Initial scopes:

```text
servers:read
metrics:read
services:read
audit:read
```

The service credential is stored in the MCP process environment or an OS-level secret file readable only by the MCP service account. It is never exposed to browser JavaScript, ChatGPT tool output, Git, or agent configuration.

The existing process-wide `PLATFORM_API_TOKEN` may remain temporarily for backward compatibility while a scoped service-principal authentication model is introduced. MCP production traffic must use the scoped principal before the milestone is considered complete.

## 13. Django Control API for MCP and Other Clients

MCP must not read Django models or PostgreSQL directly. It uses stable REST endpoints so the same control plane can support the Next.js dashboard, CLI clients, future mobile clients, or other internal agents.

Read API:

```text
GET /api/control/v1/servers/
GET /api/control/v1/servers/{server_id}/
GET /api/control/v1/servers/{server_id}/metrics/
GET /api/control/v1/servers/{server_id}/services/
GET /api/control/v1/servers/{server_id}/services/{unit_name}/
GET /api/control/v1/audit/
```

The API enforces principal scopes. MCP does not implement authorization policy independently beyond refusing to expose tools outside its configured read-only surface.

## 14. MCP Tool Contracts

### `vps_list_servers`

Input:

```json
{}
```

Returns registered servers with safe identity and freshness fields.

### `vps_get_server`

Input:

```json
{
  "server_id": "optional UUID"
}
```

If omitted, resolve the default active server.

### `vps_get_metrics`

Input:

```json
{
  "server_id": "optional UUID"
}
```

Returns server identity, metrics, `collected_at`, `age_seconds`, and `stale`.

### `vps_list_services`

Input:

```json
{
  "server_id": "optional UUID",
  "status": "optional active-state filter"
}
```

Returns allow-listed service snapshots for the selected/default server.

### `vps_get_service`

Input:

```json
{
  "server_id": "optional UUID",
  "service_name": "required exact unit name"
}
```

Returns one service snapshot. No fuzzy command or shell interpretation is permitted.

### `vps_get_recent_audit_events`

Input:

```json
{
  "server_id": "optional UUID",
  "limit": 20
}
```

`limit` is bounded server-side. Audit output is sanitized and read-only.

## 15. Structured Errors

MCP normalizes control-plane failures and must not expose raw Django exceptions or stack traces.

Defined error codes include:

```text
server_not_found
default_server_not_configured
server_offline
metrics_unavailable
service_not_found
forbidden
control_plane_unavailable
invalid_request
```

Example:

```json
{
  "error": "server_offline",
  "message": "Server has not reported recently.",
  "last_seen_at": "2026-09-01T15:00:00Z"
}
```

Responses must never include:

- Django `SECRET_KEY`,
- Authorization headers,
- enrollment secrets,
- agent bearer tokens,
- MCP service credentials,
- database credentials,
- raw stack traces.

## 16. Audit Model

Audit remains a control-plane responsibility.

Events include at minimum:

```text
agent.enrolled
agent.heartbeat.accepted
agent.credential.revoked
mcp.servers.read
mcp.metrics.read
mcp.services.read
mcp.audit.read
```

High-frequency heartbeat audit events may be aggregated or sampled to avoid unbounded audit noise; security-relevant enrollment, credential, authentication, and future write-operation events must remain durable.

MCP read events should identify the service principal and requested server, but never record bearer tokens.

## 17. Future Operation Model

The schema for future typed writes may be introduced during this migration, but no write operation is exposed through MCP v1.

Proposed `Operation` model:

```text
id                UUID
server_id         UUID
kind              enum
payload           JSON
status            queued | claimed | running | succeeded | failed | cancelled
requested_by      principal reference/text
idempotency_key   string
created_at        datetime
claimed_at        datetime nullable
started_at        datetime nullable
finished_at       datetime nullable
result            JSON nullable
error             JSON nullable
```

Allowed future kinds are explicit enums such as:

```text
service.start
service.stop
service.restart
deployment.deploy
deployment.rollback
backup.create
nginx.reload
```

There will never be an operation kind that accepts arbitrary free-form shell execution.

Future agents will claim typed operations outbound from the control plane, execute an allow-listed executor, and return structured results. That future capability requires a separate design/approval milestone for RBAC, approvals, sudo helpers, idempotency, rollback behavior, and write-action safety.

## 18. Backward-Compatible Migration

The migration avoids breaking the existing MVP in one deployment.

### Stage A: additive schema and APIs

Add UUID server identity, `is_default`, agent credential/enrollment models, heartbeat API, freshness calculation, scoped service principal model, and new read control API. Keep existing `agent_url`, `AgentClient`, manual `/sync`, and `PLATFORM_AGENT_TOKEN` temporarily working.

### Stage B: agent outbound mode

Update the agent to enroll and send heartbeat. Verify the primary VPS appears correctly through the new API while the old sync path still exists as a fallback.

### Stage C: MCP read path

Deploy MCP on `127.0.0.1:3060`, connect it through the already-created Secure MCP Tunnel, and validate all read tools from ChatGPT.

### Stage D: deprecate pull path

After heartbeat and MCP are stable, mark `agent_url`, manual pull sync, and the shared agent token deprecated. Remove them in a later cleanup change rather than in the first multi-server migration.

## 19. Security Boundaries

The design enforces these invariants:

1. No arbitrary shell tool exists in Agent, Django, or MCP.
2. Browser never receives agent or MCP service credentials.
3. ChatGPT never receives agent credentials.
4. Secondary agents require outbound HTTPS only.
5. Every server has an independent revocable credential.
6. MCP has a separate scoped read-only service principal.
7. MCP binds to localhost; Secure MCP Tunnel is the external bridge.
8. Host service inventory remains allow-listed.
9. Django remains the only system of record for server state and authorization.
10. Future privileged actions must be typed, audited, idempotent where applicable, and separately approved before exposure.

## 20. Testing Strategy

### Unit tests

- default server resolution,
- one-default-server invariant,
- heartbeat freshness calculation,
- token hashing and verification,
- enrollment expiry and one-time use,
- scope checks,
- MCP input validation,
- MCP error normalization,
- MCP response serialization.

### Django API tests

- valid/invalid/expired enrollment,
- enrollment token cannot be reused,
- server credentials are isolated,
- revoked credential cannot heartbeat,
- heartbeat updates only its own server,
- service snapshots remain scoped by server,
- metrics and service read APIs enforce scopes,
- audit API enforces scope and result bounds,
- default server selection is deterministic.

### MCP integration tests

Use the official SDK's in-process client/server path where possible so tool contracts can be tested without opening a network port.

Verify:

- tool discovery,
- structured inputs and outputs,
- default server fallback,
- explicit server selection,
- stale/offline reporting,
- normalized unavailable/forbidden errors,
- no secret leakage.

### Production end-to-end test

```text
ChatGPT
  -> Secure MCP Tunnel
  -> 127.0.0.1:3060/mcp
  -> Django read API
  -> latest agent heartbeat state
```

The final acceptance test is a real ChatGPT invocation that lists the primary server, reads current CPU/RAM/disk/uptime, and lists real allow-listed systemd services without manual SSH and without exposing any secret.

## 21. Deployment Units

Expected services on the primary VPS after this milestone:

```text
digitalafarin-platform-api.service
digitalafarin-platform-web.service
digitalafarin-platform-agent.service
digitalafarin-platform-mcp.service
digitalafarin-platform-mcp-tunnel.service
```

The MCP and tunnel services run under dedicated non-root service accounts where practical. Agent privilege remains minimal in the read-only milestone.

## 22. Non-Goals

Explicitly out of scope for this design:

- start/stop/restart from ChatGPT,
- deployment or rollback,
- arbitrary terminal/file-manager access,
- Nginx or SSL mutation,
- database create/restore mutation,
- Docker/Kubernetes orchestration,
- multi-tenant customer access,
- billing,
- public MCP endpoint,
- exposing host-agent ports to the internet,
- historical metrics/time-series observability.

## 23. Reference Constraints

Implementation must follow the current stable official MCP Python SDK v2 release line and Streamable HTTP transport. OpenAI Secure MCP Tunnel is the supported connection mechanism for this private/local MCP server. The MCP server remains local-only and is not directly published to the public internet.
