# Migration execution & production readiness

**Status: PENDING LOCAL EXECUTION.** This branch contains import tooling and CI gates, not imported source bytes. It intentionally does not touch production.

## Run in a disposable full Git checkout

```bash
git clone https://github.com/rahi62/digitalafarin-platform.git
cd digitalafarin-platform
git checkout feat/import-agency-wordpress-workspaces
bash scripts/import-mcp-workspaces.sh
bash scripts/import-mcp-workspaces.sh --execute
```

Both upstream repositories are private and require GitHub credentials in the environment running `git fetch`. Run only in a secure local workstation context. The script imports source and full history under `services/agency` and `services/wordpress`; it also writes exact SHA provenance records. On any failure, stop and inspect commits; do not blindly rerun a partial import.

## CI acceptance gates

- Both workspaces present, complete lockfiles, clean `npm ci`, `npm run check`, `npm test`, `npm run build`.
- Platform Django check. Existing VPS control plane and host-agent regressions must be run separately.
- No OAuth tokens, `.env`, credential caches, user data or `node_modules` in commits.
- Identify the WordPress GSC Broker and encrypted OAuth credential ownership *before* extracting a shared adapter.
- Validate local Claude Desktop stdio handshake, authorized GSC calls, missing-token behavior, Sheets offline append/restart/reconciliation and unchanged CMS write security gates.
- Data model migration and endpoint compatibility checks before declaring production-ready.

## Anti-duplication contract

**Canonical implementation:** existing WordPress MCP GSC broker until feature-parity extraction is verified.

The independent GSC module built as a draft in Agency PR #5 must **not** be imported as a second production OAuth provider. Integrate Agency tasks/decisions and Sheets audit after baseline import; preserve scope isolation. A package move is not permission to drop existing security guards.

## Definition of done

Only mark a milestone done with committed source, passing CI, reproducible local runtime, live authorized integration checks, and documented rollback. No archiving of source repositories and no production deploy without explicit release approval.
