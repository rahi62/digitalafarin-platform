# DigitalAfarin Platform — Integration Engineering Standards v1.0

**Status:** migration acceptance contract; no production deployment authorized.

## Architectural boundaries

DigitalAfarin Platform is the sole long-term source repository. Consolidation means **one source of truth, not one giant process**. Maintain separately deployable, testable bounded contexts:

| Context | Owns | Does not own |
|---|---|---|
| Platform Core | account/access policy, configuration references, infrastructure control plane | WordPress article content |
| Agency | projects, tasks, approvals, decisions, specialist workflow | WordPress REST/OAuth credential persistence |
| WordPress | site/credential brokerage, CMS read/write, template operations, GSC integration until canonical extraction | Agency project state |
| SEO | canonical intent map, Money Page inventory, reports and evaluations | raw immutable CMS history |
| Audit | event schema, durable local outbox, sync status and Sheets projection | Google Sheets as authoritative transaction store |
| Desktop Adapter | stdio transport and capability exposure | separate business logic and database |

**Critical:** Existing WordPress repo has a GSC integration and encrypted credential broker. Preserve this instead of maintaining two long-term OAuth implementations.

## Import rules

1. Inventory executable entry points, transport, persistence, migrations, env vars, secrets, licenses, CI, deploy and tests *before* importing.
2. Preserve upstream commit provenance (document source repo, exact commit SHA, import date) for each subtree.
3. Move sources without reshaping behavior in the first commit. Refactors must follow only after baseline test parity.
4. Use workspace tooling selected from actual project lockfiles. Do not mix competing lockfiles by guesswork.
5. No cross-package imports into private internals. Expose typed contracts and versioned adapters.
6. No direct dependency from Agency on WordPress datastore schema. Interactions use narrow client interfaces.
7. No host-management permissions in Claude Desktop's SEO-only MCP scope.
8. No network server needed for stdio mode; the Google APIs still use outgoing HTTPS.
9. No production or source-repository archival until cutover plus rollback test approval.

## Contract standards

- All site identifiers and GSC property identifiers are explicit; never infer property equivalence.
- Use ISO 8601 UTC timestamps for events; include display-local timezone only at presentation layer.
- `event_id` is unique UUID, `correlation_id` groups one workflow, `project_id` references the Agency project, and `site_id` is a stable configured identifier.
- Changes record `event_type`, `action`, `actor`, `approval_reference`, `before_reference`, `after_reference`, `result`, `source_system`, `commit_sha` where applicable.
- Separate `proposed`, `approved`, `attempted`, `executed`, `verified`, `reverted` states. Never log proposed as performed.
- `schema_version` mandatory; all changes to shared contracts require compatibility tests and migration.
- Input validation at MCP boundary and service adapter. Redact credentials and personally identifying form data.
- HTTP failures return typed, non-sensitive errors. Never expose third-party raw error bodies to model output.

## Local state & Sheets projection

SQLite is the local durable outbox. Google Sheets is the human-readable reporting projection, **not** the only copy of business-critical audit history.

Sync protocol:
1. Persist an event locally before acknowledging success.
2. Mark pending events with a lease/lock to prevent simultaneous sync workers.
3. Read existing remote event IDs, reconcile and append missing rows.
4. After successful confirmation, update local sync state.
5. Handle ambiguous network failures by leaving pending and reconciling before retry.
6. Monitor pending/failed counts, retry with bounded backoff and surface operator-visible errors.
7. Recognize Google Sheets cannot enforce uniqueness; cross-process exactly-once requires stronger infrastructure. Avoid promising strict exactly-once delivery.

Keep sensitive credentials outside Sheets. Limit workbook sharing and OAuth scopes.

## OAuth & access control

- GSC uses read-only scopes and explicit property allowlists.
- Sheets integration uses the minimum viable scope for specified workbook read/append.
- OAuth credentials encrypted at rest where persisted, never checked into Git, logs or chat.
- Different auth principals for desktop, production control plane and CMS writes.
- Authorization enforced server-side even when the assistant is instructed not to write.
- Agency approval history is not a substitute for confirming a destructive operation in the execution context.

## Regression and quality gates

Each milestone requires evidence attached to its PR:

| Gate | Required evidence |
|---|---|
| Baseline | existing tests pass before import; exact upstream SHA documented |
| Static | TypeScript/Python checks, lint, dependency/secret scan |
| Unit | URL identity, date ranges, event state transitions, access boundaries |
| Integration | GSC OAuth and quotas/error paths, CMS mock, Sheets reconciliation |
| Desktop | local stdio handshake, list tools, invoke authorized/unauthorized tools |
| Recovery | offline write, process restart, sync retry, interruption in middle of append |
| Compatibility | existing Platform Django/Next/VPS workflows and WordPress tools unaffected |
| Deployment | explicit approval, staged rollout, health check and rollback verification |

No `main` merge when lockfiles are inconsistent, runtime fails, credentials are missing for required integration tests or release evidence is absent. Test skips must be clearly documented and considered blockers where applicable.

## Sequenced delivery

- **M0** Inventory, dependency graph, shared contract draft and risk register.
- **M1** Import unchanged Agency + WordPress sources with provenance and baseline parity.
- **M2** Establish shared interfaces, feature flags and permissions.
- **M3** Consolidate GSC integration and OAuth brokerage.
- **M4** Add local SQLite outbox and Sheets projection with safety tests.
- **M5** Build desktop stdio adapter and test Claude Desktop behavior.
- **M6** Stage dashboard integration; validate existing control plane and production behavior.
- **M7** Complete cutover after written operator approval, then consider archiving legacy repos.

## Definition of done

A feature is not complete merely because code was pushed. It is complete only after a reproducible build, passing automated tests, integration smoke tests, credential-boundary review, real desktop invocation, operator docs, observability and rollback procedure. Unsupported claims (for example, 'live GSC connected') must not be made before they are verified.
