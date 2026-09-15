# Typed Operation Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe typed, audited, outbound-only service operations and bounded redacted logs.

**Architecture:** Django owns a transactional operation queue and state machine. Agents claim work outbound and dispatch exact typed handlers; Control API, MCP, and Admin UI expose only scoped operation contracts.

**Tech Stack:** Django 5/DRF, Python 3.11+, httpx/FastAPI agent, MCP Python SDK, Next.js 16/TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-15-operation-foundation-design.md`

## Global Constraints

- State flow is exactly `queued -> claimed -> running -> succeeded|failed`.
- Allowed kinds are `service.start`, `service.stop`, `service.restart`, and `service.logs`.
- No arbitrary shell, systemctl action, unit, journal arguments, or inbound management endpoint.
- Platform/MCP/tunnel management units are always protected.
- Persist and expose only bounded, redacted output.
- Enforce `operations:read`, `operations:create`, and `logs:read` independently.

---

### Task 1: Operation persistence and transactional state machine

**Files:**
- Modify: `apps/api/control/models.py`
- Create: `apps/api/control/migrations/0006_operations.py`
- Create: `apps/api/control/services/operations.py`
- Create: `apps/api/control/tests/test_operation_model.py`

**Interfaces:**
- Produces: `Operation`, `OperationTransitionError`, `create_operation(...)`, `claim_next_operation(...)`, `start_operation(...)`, `complete_operation(...)`.

- [ ] Write tests proving default queued state, legal transitions, illegal transition rejection, claim server binding, lease recovery, idempotent retry, and an audit row for every accepted transition.
- [ ] Run `python manage.py test control.tests.test_operation_model -v 2`; confirm failures are missing models/services.
- [ ] Add UUID identity, kind/state/payload/result/error fields, lifecycle timestamps, lease token/expiry, actor/idempotency fields, indexes and constraints.
- [ ] Implement all mutations in `transaction.atomic()` with row locking and redacted bounded failure/result normalization.
- [ ] Re-run the focused tests and `python manage.py makemigrations --check --dry-run`; require PASS.
- [ ] Commit with `feat: add audited operation state machine`.

### Task 2: Scoped Control and Agent operation APIs

**Files:**
- Modify: `apps/api/control/agent_serializers.py`
- Modify: `apps/api/control/agent_urls.py`
- Modify: `apps/api/control/agent_views.py`
- Create: `apps/api/control/operation_serializers.py`
- Modify: `apps/api/control/control_urls.py`
- Create: `apps/api/control/operation_views.py`
- Create: `apps/api/control/tests/test_operation_api.py`

**Interfaces:**
- Consumes: Task 1 operation services.
- Produces: `POST/GET /api/control/v1/operations/`, `GET /api/control/v1/operations/<uuid>/`, and agent claim/started/complete endpoints.

- [ ] Write API tests for all three scopes, strict per-kind schemas, unknown-key rejection, protected units, idempotency, server ownership, stale claim token, and log-read separation.
- [ ] Run the focused test and verify the intended 404/import failures.
- [ ] Implement serializers and views with exact response allow-lists; create calls use authenticated principal name as actor.
- [ ] Add agent endpoints bound only to `request.user.server`; never accept a server ID from the agent.
- [ ] Re-run focused API tests and the complete Django suite.
- [ ] Commit with `feat: expose scoped typed operation APIs`.

### Task 3: Agent typed execution and redaction

**Files:**
- Create: `agent/digitalafarin_agent/redaction.py`
- Create: `agent/digitalafarin_agent/operations.py`
- Modify: `agent/digitalafarin_agent/systemd.py`
- Modify: `agent/digitalafarin_agent/control_plane.py`
- Modify: `agent/digitalafarin_agent/heartbeat.py`
- Create: `agent/tests/test_operations.py`
- Create: `agent/tests/test_redaction.py`
- Modify: `agent/tests/test_control_plane.py`

**Interfaces:**
- Produces: `OperationRunner.run_once(token)`, `execute_operation(kind, payload)`, `redact(text, known_secrets=())`.

- [ ] Write failing tests proving exact subprocess arrays/timeouts, protected-unit denial, unsupported-kind denial, 200-line and byte caps, token/URL/key/database redaction, and claim-start-complete request ordering.
- [ ] Run the focused Agent tests and confirm failures arise from missing behavior.
- [ ] Implement validators and four handlers using fixed argv with `shell=False`; add structured client methods.
- [ ] Integrate one-operation polling into the existing outbound heartbeat loop with sanitized exception logging.
- [ ] Run Agent focused and full suites; run a source scan for `shell=True`, `os.system`, and free-form execution entry points.
- [ ] Commit with `feat: execute typed operations outbound`.

### Task 4: MCP operation tools

**Files:**
- Modify: `mcp/digitalafarin_vps_mcp/control_plane.py`
- Modify: `mcp/digitalafarin_vps_mcp/server.py`
- Modify: `mcp/tests/test_control_plane.py`
- Modify: `mcp/tests/test_server.py`
- Modify: `mcp/tests/test_server_contract_static.py`

**Interfaces:**
- Produces: narrow create/read MCP tools for typed service operations.

- [ ] Write failing tool/client tests for each allowed kind, operation reads, logs, validation errors, and absence of generic command tools/arguments.
- [ ] Run focused MCP tests and verify missing-method/tool failures.
- [ ] Implement client methods and MCP tools whose typed parameters construct server-side validated payloads.
- [ ] Re-run MCP full suite and static contract checks.
- [ ] Commit with `feat: add typed operation MCP tools`.

### Task 5: Operational Admin hooks

**Files:**
- Modify: `apps/web/lib/control-plane.ts`
- Create: `apps/web/lib/operations.test.ts`
- Create: `apps/web/app/operations/page.tsx`
- Create: `apps/web/app/operations/[operationId]/page.tsx`
- Modify: `apps/web/components/SidebarNav.tsx`
- Modify: `apps/web/app/servers/[serverId]/page.tsx`

**Interfaces:**
- Produces: server-only typed operation requests and minimal list/detail/action UI.

- [ ] Write failing tests for request paths, typed bodies, log permission behavior, and response normalization without secret fields.
- [ ] Run `npm test`; confirm failures identify missing client functions.
- [ ] Extend the server-only client to support JSON writes and render operational pages/actions without a free-form input.
- [ ] Run Web tests and ESLint.
- [ ] Commit with `feat: add operation admin hooks`.

### Task 6: Stage A regression and acceptance

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: Tasks 1-5.
- Produces: Stage A acceptance evidence and accurate operator documentation.

- [ ] Update documented scopes, endpoints, state lifecycle, protected-unit policy, and outbound execution model.
- [ ] Run Django full tests/check/migration check, Agent full suite, MCP full suite, Web tests/lint/build, `git diff --check`, and security scans.
- [ ] Record exact commands/results in the working log; fix any regression test-first.
- [ ] Commit with `docs: document typed operation foundation`.
- [ ] Begin Stage B immediately after all checks pass.
