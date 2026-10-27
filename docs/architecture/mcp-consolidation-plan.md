# DigitalAfarin Platform consolidation — migration plan

Status: **architecture accepted / discovery in progress**. This document does not authorize a production deployment.

## Verified repository facts (2026-10-27)

- `digitalafarin-platform`: Django control plane, Next.js web UI, Python VPS MCP, host agents and deployment tooling.
- `digitalafarin-wordpress-mcp`: Node.js/TypeScript WordPress MCP with existing Google Search Console read-only tools, Dashboard/Broker integration and PostgreSQL credential handling.
- `digitalafarin-agency-mcp`: Node.js/TypeScript Agency project/tasks/decisions MCP.
- Existing Agency development: [PR 3](https://github.com/rahi62/digitalafarin-agency-mcp/pull/3), [PR 4](https://github.com/rahi62/digitalafarin-agency-mcp/pull/4), [PR 5](https://github.com/rahi62/digitalafarin-agency-mcp/pull/5) remain unmerged drafts.

## Target repository layout (proposal, subject to inventory)

```text
digitalafarin-platform/
  apps/
    api/                # existing Django control plane, unchanged initially
    web/                # existing Next.js panel, unchanged initially
    claude-desktop-mcp/ # future local stdio entry point
  agent/                # existing host agents, unchanged
  mcp/                  # existing VPS MCP, unchanged
  services/
    agency/             # migrated Agency TypeScript service
    wordpress/          # migrated WordPress TypeScript service
  packages/
    integrations/
      gsc/              # single canonical GSC adapter (extract, do not duplicate)
      google-sheets/    # audit sink
    audit/              # local SQLite outbox + idempotent delivery
  docs/
```

## Guardrails

1. Do not modify the existing VPS/agent deployment path during source migration.
2. Copy source with provenance first. Preserve the complete original Git repositories and commit history; do not delete or archive until regression parity is verified.
3. Never commit OAuth tokens, site credentials, local SQLite files, secrets or production environment variables.
4. A local Claude Desktop mode must not require a VPS or inbound HTTP listener; Google API calls still require network access.
5. Keep the WordPress and Agency domains isolated with explicit interfaces and their own regression suites.
6. Use an existing GSC implementation as the starting point. Remove competing implementations only **after** feature parity.
7. Google Sheets is a reporting/audit destination, not a fully immutable transaction log. A local durable outbox is the source for pending writes. Avoid claiming cross-process exactly-once delivery without tests.
8. Preserve approved-permission boundaries: read-only GSC; CMS writes, redirects and publishing require separate explicit authorization.
9. No migration modifies live WordPress sites, Search Console properties or production environments.

## Delivery milestones

| Milestone | Scope | Acceptance gate |
|---|---|---|
| M0 | Repository inventory and dependency map | Files, transport, storage, OAuth ownership identified |
| M1 | Import Agency and WordPress packages with provenance | Native builds and existing tests pass unchanged |
| M2 | Consolidate GSC through an adapter | Existing analytics, inspection and sitemap tests pass |
| M3 | Local Sheets + SQLite audit subsystem | Offline append, restart recovery, reconciliation, duplicate/concurrency tests |
| M4 | Claude Desktop stdio entry point | MCP handshake, list tools and representative calls pass locally |
| M5 | Platform UI integration / shared management | Existing VPS deployment regression and permissions pass |
| M6 | Cutover and deprecation | Operator signoff, rollback documented, production untouched until approval |

## Next actions

- Establish definitive file inventories and versioned baselines from all 3 repositories.
- Decide whether WordPress MCP's existing Dashboard credential broker runs locally or needs a local adapter.
- Resolve local storage configuration for Agency, and distinguish audit storage from business database state.
- Regenerate lock files when adding dependencies, build/test on Node.js 20+ in WSL.
- Keep feature branches and draft PRs separate from `main` until verified.

## Rollback

No running services are changed during M0–M4. Restore by stopping the local desktop MCP and switching back to existing repository checkouts. Do not delete the original repos or their secrets/configuration.
