# Stage A: Typed Operation Foundation

## Goal

Provide the minimum production-ready write path needed by the migration deployment engine while preserving the existing outbound-only agent architecture and eliminating arbitrary execution surfaces.

## Scope

Stage A adds typed service operations, bounded journal reads, lifecycle audit, service-principal scopes, outbound agent execution, and operational MCP/Admin hooks. It deliberately excludes free-form shell, arbitrary `systemctl`, browser terminals, filesystem browsing, SQL consoles, and cosmetic UI work.

## Architecture

The Django control plane is the system of record. A single `Operation` envelope carries a strictly validated operation kind and JSON payload. The first allowed kinds are `service.start`, `service.stop`, `service.restart`, and `service.logs`. Each kind has a dedicated validator and agent handler; unknown keys and unknown kinds are rejected before an operation is persisted.

Agents continue making outbound HTTPS requests only. An authenticated agent claims one queued operation for its own server, reports it started, and completes it with a success or failure result. The agent exposes no inbound management route. Claiming uses a database transaction and a finite lease so concurrent agents cannot claim the same operation and abandoned claims can be recovered safely.

## Operation lifecycle

The canonical state machine is:

```text
queued -> claimed -> running -> succeeded
                            \-> failed
```

Only the control-plane transition service may change state. Transitions are idempotent where network retries are expected and reject stale claim tokens, the wrong agent/server, terminal-state mutation, and illegal ordering. Timestamps include creation, claim, start, completion, and lease expiry. Failure data uses a bounded machine code and redacted message.

Each accepted transition creates an `AuditEvent` in the same database transaction. Audit metadata includes operation UUID, kind, server UUID, previous state, new state, and actor, but never credentials, environment values, raw command output, or unredacted logs.

## Typed execution policy

Service payloads contain only an exact systemd unit name. Unit names must match the server's managed service allow-list and must not be protected. Protection is deny-first and covers:

- `digitalafarin-platform-*`
- the platform API, web, agent, MCP, and tunnel units
- DigitalAfarin MCP/tunnel/platform management services even if their configured discovery prefix would otherwise allow them

The agent invokes subprocesses with fixed argument arrays, `shell=False`, a timeout, bounded output, and no caller-controlled flags. Service mutations use only `systemctl start|stop|restart <validated-unit>`. Logs use only a fixed `journalctl` shape with bounded line count and time window.

## Log safety

`service.logs` accepts structured bounds with conservative defaults and hard maximums. The agent truncates by bytes after collection. A shared redactor removes token formats, authorization headers, URL credentials, common secret assignments, database URLs, private-key blocks, and values supplied through the secure execution secret set. The control plane stores and returns redacted text only.

Operation result payloads are schema-validated and size-limited. MCP and Admin APIs never receive agent credentials or unredacted output.

## APIs and scopes

Control-plane service principals gain:

- `operations:read`
- `operations:create`
- `logs:read`

Creating service mutations requires `operations:create`; reading operation metadata requires `operations:read`; retrieving the redacted result of `service.logs` additionally requires `logs:read`. Agent endpoints use agent credentials and are server-bound.

MCP exposes narrow tools for creating the four allowed operations and reading operation status/log results. Tool inputs mirror the strict API schemas. Admin hooks provide an operation list/detail and service action controls without introducing a general command field.

## Error handling and recovery

Operation creation rejects offline targets, invalid units, protected units, malformed payloads, unsupported kinds, and duplicate idempotency keys. Claim leases permit recovery after agent crashes. Retry of started non-idempotent work is not automatic; the terminal failure remains auditable and an operator creates a new operation.

## Testing and acceptance

TDD covers transition legality, transactional audits, claim concurrency, lease expiry, scope enforcement, server binding, typed payload rejection, protected units, subprocess argument construction, timeouts, bounded logs, redaction, MCP schemas, and Admin hooks. Stage A acceptance requires Django, Agent, MCP, and Web suites plus static scans proving no arbitrary execution interface exists.

Stage A completion immediately starts Stage B; there is no UI-polish or refactor checkpoint.
