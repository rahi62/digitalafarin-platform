# WP Agent Dashboard

Administration and integration control plane for DigitalAfarin WordPress MCP.

## Security model

- Phase 1 still uses a single administrator session; workspace/tenant roles are the next productization milestone.
- WordPress Application Passwords are encrypted at rest with AES-256-GCM.
- Product integration secrets such as Google OAuth Client Secret and Search Console Refresh Token are configured from the authenticated panel and encrypted in PostgreSQL.
- Environment variables are reserved for infrastructure secrets: database, admin authentication, session signing and the master credentials-encryption key.
- The UI never returns or renders a stored secret.
- MCP brokers are localhost-only and public Nginx access to `/api/internal/` must remain blocked.
- State-changing operations create audit records.

## Search Console product model

Hosted SaaS can use one DigitalAfarin-owned Google OAuth App configured once by the platform administrator. End customers only connect their Google account and map their Search Console properties.

White-label / self-hosted installations can enter their own Google OAuth Client ID and Client Secret from **Settings → Integrations**. The OAuth callback is derived from the deployed dashboard domain instead of being hard-coded in source code.

## Local development

```bash
cp .env.example .env.local
npm install
npm run dev
```

The PostgreSQL schema is created idempotently on the first dashboard request.
