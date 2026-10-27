# MCP monorepo imports — verified provenance

Verified against imported commits in the platform migration branch.

| Module | Original repository | Imported upstream commit | Subtree import commit | Destination |
|---|---|---|---|---|
| Agency | rahi62/digitalafarin-agency-mcp | `4b213cca04677ed4ce1c94c042f2d39757924846` | `9800ecb` | `services/agency/` |
| WordPress + GSC | rahi62/digitalafarin-wordpress-mcp | `41829b5432d5c2fc6dddd7b4bf904ed2b0d5d31b` | `bab0e5e` | `services/wordpress/` |

These are full-history `git subtree add` imports performed by the repository owner. The upstream repos remain intact.

## Baseline observations

- Agency: TypeScript + Node; source `package.json` declares `0.2.0` and database/argon2/vitest dependencies. Its imported `package-lock.json` still describes the `0.1.0` dependency set. **The lockfile requires regeneration** before `npm ci` can pass.
- WordPress: TypeScript + Node; includes existing read-only GSC tools and a Dashboard/credential broker. Avoid a second long-term OAuth implementation.
- The platform's existing Python MCP remains the protected VPS control-plane adapter.
- Agency PR #5 is a separate unmerged prototype for Desktop/GSC/Sheets; do not import its duplicated GSC module as a second provider.

## Required next validation

1. Within `services/agency` run `npm install --package-lock-only` and commit only the updated lockfile.
2. Execute `npm ci && npm run check && npm test && npm run build` separately for both imported modules.
3. Run root Platform regression/CI checks before refactoring.
4. Record exact test outcomes in the migration PR; no test run has been confirmed yet.
5. Design Desktop stdio tool composition without exposing the VPS-operation scopes to SEO clients.

**No production deployment, merge or source archival is authorized by this record.**
