# Agency MCP — Claude Desktop local smoke test

The **imported** Agency MCP now has a dedicated `stdio` entrypoint. This is deliberately separate from the existing HTTP application and does not change its production configuration.

## PowerShell commands (from the root of the platform checkout)

```powershell
cd services/agency
npm install --package-lock-only
npm ci
npm run check
npm test
npm run build
```

**Before committing:** review changes to `package-lock.json` and confirm no secrets are added. The imported Agency lockfile was stale at import time.

## Claude Desktop configuration — Windows Node.js

Use absolute Windows paths. Claude Desktop config is at:

`%APPDATA%\\Claude\\claude_desktop_config.json`

Example (replace the full path to your checkout):

```json
{
  "mcpServers": {
    "digitalafarin-agency-local": {
      "command": "node",
      "args": [
        "D:\\projects\\next-drf projects\\digitalafarin-platform-clean\\services\\agency\\dist\\local.js"
      ],
      "env": {
        "STORE_DRIVER": "json",
        "DATA_FILE": "D:\\projects\\next-drf projects\\digitalafarin-platform-clean\\services\\agency\\data\\agency-local.json"
      }
    }
  }
}
```

No port is opened by this `stdio` process. The Agency's existing `createMcpServer()` tool registrations are reused.

## Acceptance checks

1. `npm run check`, `npm test` and `npm run build` complete without errors.
2. Launch Claude Desktop and verify the tool `agency_get_team` is visible.
3. Call `agency_list_projects` and confirm the local JSON store works.
4. Close and restart Claude Desktop; verify project data remains available.
5. Verify WordPress MCP and GSC integrations remain **separate and unchanged** until canonical interfaces are established.
6. Inspect logs for token exposure and ensure `stdout` contains no debug printing.

## Not yet delivered

- A single unified Claude Desktop MCP combining Agency, WordPress and GSC.
- Local WordPress broker/credential flow.
- Google Sheets audit migration and OAuth.
- Tested lockfile, CI green status and production readiness.

Do not mistake an entrypoint and documentation for verified end-to-end behavior.
