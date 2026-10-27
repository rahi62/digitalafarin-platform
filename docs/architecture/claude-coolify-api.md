# Claude Desktop ↔ Coolify (read-only pilot)

This adapter is **local and opt-in**. It is part of the existing single DigitalAfarin MCP Hub and adds no new Claude custom connector. It does not modify the Platform VPS MCP.

## Capabilities in this phase

- `coolify_list_servers` → `GET /api/v1/servers`
- `coolify_list_applications` → `GET /api/v1/applications`
- `coolify_list_projects` → `GET /api/v1/projects`

There are no mutation, deploy, delete, or arbitrary-request tools. HTTP requests require HTTPS (except localhost), have a 12-second timeout, and do not follow redirects.

## Prerequisites

In Coolify, enable API access (self-hosted: Settings → Advanced), create a separate **read-only** team-scoped API token, and if configured, allow the Claude Desktop computer's IP. Never use root credentials. Do not send the token in chat or commit it to Git.

Set `COOLIFY_URL` to the instance origin, e.g. `https://coolify.example.com` (not `/api/v1`). Set `COOLIFY_TOKEN` using a local, protected environment/secret mechanism. The Claude Desktop process and child processes must receive both environment variables. The hub starts Coolify only when both are present; otherwise the previous Agency + WordPress/GSC tools stay intact.

## Build

```powershell
git pull origin feat/import-agency-wordpress-workspaces
cd services/agency
npm run check
npm run build
npm run smoke:unified-local
```

Smoke test currently verifies Agency + WordPress/GSC; it is not a live Coolify API connectivity test. After setting runtime variables, restart Claude Desktop and ask Claude to list Coolify servers. Confirm the exposed server names match the intended Coolify team. Never paste raw API responses if they contain sensitive data.

## Future separate approval

Deploy/restart/stop require a dedicated least-privilege token with `deploy`, operation allowlists, explicit confirmation, and a separate safety/QA review. Production remains untouched until authorized.
