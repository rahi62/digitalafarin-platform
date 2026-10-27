# Claude Desktop — direct Google Search Console (read-only)

## Scope

An opt-in **local-only** MCP entrypoint: `services/wordpress/src/gsc-readonly-local.ts`.
No WordPress broker, no Site Kit, no Sheets integration, no custom comparison/SEO algorithms, no mutation API, no production deployment.

Two tools:

- `gsc_list_properties` → Google `GET /webmasters/v3/sites`
- `gsc_read_performance` → Google `POST /webmasters/v3/sites/{siteUrl}/searchAnalytics/query` (a data-reading query)

The request tool supports dates, dimensions, filters, pagination and row limits. Claude analyzes the returned rows; the user's existing Google Sheets integration stores workflow/content planning.

## OAuth prerequisites

1. In Google Cloud Console, select a project with Search Console API enabled and configure the OAuth consent screen.
2. Create a Google **Desktop** OAuth client, authorize the Google account that has GSC property access, requesting only `https://www.googleapis.com/auth/webmasters.readonly`, and obtain an offline refresh token via an approved local OAuth flow. If the OAuth app is in Testing mode, refresh-token lifetimes can be restricted.
3. Store `GSC_CLIENT_ID`, `GSC_CLIENT_SECRET`, `GSC_REFRESH_TOKEN` locally in a protected secret store/environment for Claude Desktop. Do not commit credentials, put them in a public .env, paste them into chat, or share config screenshots containing them.
4. Restart Claude Desktop after setting the variables; they must reach the hub's Node process. When all three exist, the hub uses direct GSC instead of its previous WordPress/GSC broker process. Legacy behavior is preserved when not configured.
5. Restrict the Google account/property access to only necessary properties. Never request the broader `webmasters` scope.

## Verify from PowerShell (no secrets needed for compilation)

```powershell
git pull origin feat/import-agency-wordpress-workspaces
cd services/wordpress
npm run check
npm test
npm run build
cd ../agency
npm run check
npm run build
npm run smoke:unified-local
```

The smoke test checks tool discovery only in the configured mode, plus a basic Agency call. **It does not prove Google OAuth connectivity.** In Claude Desktop, first call `gsc_list_properties`; only after that succeeds, test `gsc_read_performance` on one property and a short valid date range.

## Security constraints and limitations

- MCP defines no write/delete tools; only fixed allowlisted Google endpoints are called.
- Google refresh tokens are handled in memory at runtime; no token logging or persistence is implemented.
- Access to GSC depends on authorized Google identity and property permissions.
- Search Analytics can omit/anonymize low-volume rows and returns top results rather than complete raw exports.
- Authorization is **not** established until a real `gsc_list_properties` call succeeds.
- Deployment, Coolify work, and main branch changes remain out of scope.
