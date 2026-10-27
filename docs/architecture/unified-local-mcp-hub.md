# Unified local MCP hub — Agency + WordPress/GSC

Status: **implementation committed; build and end-to-end verification pending**.

This hub is an opt-in **local Claude Desktop** stdio process. It starts two separate Node child MCP processes and proxies their existing tool definitions and calls:

```text
Claude Desktop
    └─ stdio DigitalAfarin Local MCP Hub (services/agency/dist/unified-local.js)
         ├─ stdio Agency (services/agency/dist/local.js)
         └─ stdio WordPress + GSC (services/wordpress/dist/local.js)
```

**Explicit exclusions:** Python VPS MCP, Control Plane operations, Google Sheets (not yet integrated), network listener, shared secrets, new OAuth logic. Production services are unaffected.

## Windows PowerShell build

From `digitalafarin-platform-clean` root:

```powershell
git pull origin feat/import-agency-wordpress-workspaces
cd services/agency
npm install --package-lock-only
npm ci
npm run check
npm test
npm run build
cd ../wordpress
npm ci
npm run check
npm test
npm run build
cd ../agency
npm run start:unified-local
```

The final process waits for MCP protocol input. Stop it with Ctrl+C. No user-visible response on stdout by itself is normal.

Claude Desktop config (`%APPDATA%\\Claude\\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "digitalafarin-local": {
      "command": "node",
      "args": [
        "D:\\projects\\next-drf projects\\digitalafarin-platform-clean\\services\\agency\\dist\\unified-local.js"
      ]
    }
  }
}
```

Adapt the path to the actual checkout; merge the `digitalafarin-local` entry into existing config rather than overwriting other servers.

## Verification gates

- Both `npm run check`, `npm test`, `npm run build` pass, and Agency lockfile updated and committed.
- Claude Desktop lists `agency_get_team`, `wordpress_list_sites`, `gsc_list_sites` once each, with no duplicate names.
- `agency_get_team` responds. WordPress/GSC operations still require their existing registered-site broker and valid credentials.
- Restart Desktop. Check that no HTTP port was opened by local hub and stdout did not contain non-MCP debug logs.
- Test error behavior for unavailable broker and revoked GSC OAuth without disclosing secrets.
- Ensure no VPS operation tool is visible from this hub.

The tool hub currently reflects tool definitions obtained at startup. To refresh them, restart the Desktop MCP process. **Do not merge/deploy until the build, security, and functional gates are verified.**
