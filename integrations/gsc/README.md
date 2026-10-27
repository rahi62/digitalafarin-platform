# DigitalAfarin GSC Connector

A **standalone, local, read-only** Google Search Console connector for Claude Desktop.

> Status: new isolated implementation branch. This folder is independent of the legacy WordPress dashboard, Agency MCP, Coolify adapter, VPS agents and deployment engine. No deployment or migration has been performed.

## Product contract

- **One install, multiple Google accounts and GSC properties.** Each installation can configure its own Google OAuth client in the local settings UI, then authorize one or more Google accounts. No site runtime dependency: WordPress, Next.js, Django, Laravel and static sites all work because GSC is property-based.
- **Read-only** Google OAuth scope: `https://www.googleapis.com/auth/webmasters.readonly`.
- MCP endpoints: list connected accounts and properties, read performance with filters/dimensions/pagination, inspect indexed URLs and read sitemaps. No indexing requests, API mutations, deployment or WordPress tools.
- Claude handles comparisons and SEO analysis. Google Sheets remains handled by Claude's existing connector.
- **Minimal local UI** for Connect Google / Add Account / Properties / Reconnect / Disconnect / MCP status. Light-only, native RTL Persian; no analytics dashboards.
- **One Node package and one `node_modules`** for this connector. No Next.js, PostgreSQL, Express or Electron required.
- OAuth starts from the UI and uses the system browser, `state` + PKCE, a loopback redirect URI, and exact callback validation. Client ID and client secret configuration are provided in the UI per installation when required; never paste OAuth credentials in chat or commit them.
- Refresh tokens must be stored locally with OS-backed credential protection or another reviewed mechanism before real accounts are connected. Do not replace this with raw JSON, `.env` tokens or code constants.
- HTTP UI listens only on `127.0.0.1`; protect mutation endpoints from cross-site requests and DNS rebinding. MCP communicates over local `stdio` and never opens an external listening port.
- Both the settings UI and MCP use one small shared core. Avoid MCP-to-MCP process bridges.

## Planned layout

```text
integrations/gsc/
  package.json
  src/
    index.ts             # local CLI: settings + stdio
    mcp.ts               # raw read-only GSC tools
    oauth.ts             # OAuth lifecycle and PKCE
    google-api.ts        # GSC API client
    store.ts             # protected local account storage
    settings.ts          # tiny local HTML UI
  tests/
  README.md
```

## Acceptance gates

1. `npm ci`, TypeScript check, and automated unit/integration tests pass in isolation.
2. Settings work with no WordPress/Coolify/Agency services or PostgreSQL.
3. Connecting two Google accounts shows each account's independently granted properties; revoking one does not affect the other.
4. Claude Desktop discovers only read-only GSC tools and queries a property selected by its exact identifier.
5. No tokens in logs, chat output, stdout, browser URLs or source control.
6. Original platform services remain unchanged; merge to `main` and production require separate approval.

The existing `feat/import-agency-wordpress-workspaces` branch is **not** a prerequisite.


## Current implementation (2026-10-27)

The first localhost settings UI and Windows-protected multi-account storage were implemented in this branch. **They have not yet passed a local build or live Google authorization test.**

From the `integrations/gsc` folder on Windows:

```powershell
npm install
npm run check
npm run build
npm test
npm run settings
```

Open **http://127.0.0.1:47861/** in your browser. In Google Cloud Console, enable the Search Console API, create a **Desktop app** OAuth client with the single read-only GSC scope, paste the generated **Client ID** in Settings, then use **Add Google account**.

The UI listens exclusively on IPv4 loopback and applies OAuth `state` and PKCE. Each refresh token is encrypted using Windows DPAPI `CurrentUser` and remains on the local machine. Connected accounts can be removed individually. Click **View properties** to perform a live read-only connectivity check.

The MCP entrypoint is `node dist/index.js` and offers `gsc_list_accounts`, `gsc_list_properties` and `gsc_search_performance`. Claude Desktop setup must be updated explicitly after successful local tests.

### Important outstanding checks before connecting production Google accounts

- Validate Google Desktop OAuth code/token exchange in the user's real Google Cloud configuration; certain desktop OAuth setups may require the generated `client_secret` during token exchange despite Google documents describing it as optional. The initial implementation currently accepts only the Client ID.
- Confirm the settings UI's origin/host restrictions and account-removal CSRF protections in security review.
- Verify Windows DPAPI portability, failure handling, and token encryption test coverage.
- Expand raw read-only MCP endpoints for URL inspection/sitemaps if required.
- Confirm no duplicate or leaked credentials when moving from old connectors.
- Confirm CI check/build/tests before merging. No production deployment or automatic migration has been made.

## Claude Desktop: local MCP registration (after build and OAuth test)

Open the Claude Desktop config file at `%APPDATA%\\Claude\\claude_desktop_config.json` and **merge** this entry into its existing `mcpServers` object; do not overwrite other servers:

```json
{
  "mcpServers": {
    "digitalafarin-gsc": {
      "command": "node",
      "args": ["D:\\projects\\next-drf projects\\digitalafarin-platform-clean\\integrations\\gsc\\dist\\index.js"]
    }
  }
}
```

Update the path for the actual local checkout. Restart Claude Desktop. From its tools, first call `gsc_list_accounts`, choose an account ID, then `gsc_list_properties` and `gsc_search_performance`. Extra read-only tools: `gsc_list_sitemaps` and `gsc_inspect_url`. You do **not** need the WordPress dashboard, PostgreSQL or a remote MCP tunnel.

**Security / compatibility:** OAuth is a prototype until verified against a real desktop OAuth client and the local settings endpoints are security-tested. Keep the connector in development; do not distribute it or link a sensitive production Google account yet.
