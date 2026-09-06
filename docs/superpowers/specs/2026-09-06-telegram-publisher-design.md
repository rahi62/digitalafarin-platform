# Telegram Publisher Design

Date: 2026-09-06
Status: Approved for implementation planning
Repository: `rahi62/digitalafarin-platform`
Branch: `feat/telegram-publisher`

## Goal

Add a secure Telegram publishing subsystem to DigitalAfarin Platform so ChatGPT can publish content to one or more Telegram channels through a dedicated MCP toolset, while channel configuration is managed from a simple web UI at `https://bot.digitalafarin.ir`.

## Scope

Phase 1 is a publisher only. The bot does not ingest Telegram messages and does not call OpenAI APIs. ChatGPT remains the reasoning/content layer; the platform only exposes controlled publishing actions.

Required capabilities:

- Manage multiple Telegram channels by stable alias such as `seo`, `ai`, or `digitalafarin`.
- Store Telegram bot credentials securely outside Git and outside browser-delivered JavaScript.
- Enable/disable channels without redeploying.
- Test whether the configured bot can post to a channel.
- Publish a text message to one selected channel from ChatGPT through MCP.
- Keep an audit trail of publish/test attempts and outcomes.
- Provide a simple authenticated admin UI at `bot.digitalafarin.ir`.
- Keep the Telegram write surface isolated from the existing read-only VPS MCP.

## Architecture

```text
ChatGPT
  |
  v
OpenAI Secure MCP Tunnel
  |
  v
Telegram MCP (localhost-only)
  |
  v
Django Control Plane API
  |                 |
  |                 +--> PostgreSQL: channels + audit log
  v
Telegram Bot API
  |
  v
Telegram Channels

Browser
  |
  v
https://bot.digitalafarin.ir
  |
  v
Next.js Admin UI
  |
  v
Django Control Plane API
```

The existing VPS MCP remains read-only and separate. Telegram write actions use a dedicated MCP service, dedicated service principal, dedicated environment file, and dedicated systemd unit.

## Repository Layout

The feature stays in the existing monorepo but uses isolated modules:

```text
digitalafarin-platform/
├── apps/
│   ├── api/
│   │   └── telegram_publisher/
│   └── web/
│       └── app/bot/
├── telegram-mcp/
│   └── digitalafarin_telegram_mcp/
├── infra/
│   ├── nginx/bot.conf.example
│   └── systemd/
│       ├── digitalafarin-telegram-mcp.service
│       └── digitalafarin-telegram-mcp-tunnel.service
└── docs/
```

The final directory names may follow existing repo conventions where necessary, but module boundaries remain the same.

## Django Data Model

### TelegramBotCredential

Phase 1 uses a single active bot credential for all configured channels.

Fields:

- `name`
- `is_active`
- `token_ciphertext`
- `created_at`
- `updated_at`

The raw token must never be returned by the API after creation. The API may return only a masked indicator such as `configured: true`.

Encryption key is supplied through server environment, for example `TELEGRAM_CREDENTIAL_ENCRYPTION_KEY`, never stored in the database or Git.

### TelegramChannel

Fields:

- `public_id` UUID
- `alias` unique, lowercase, stable MCP-facing identifier
- `name` display name
- `chat_id` Telegram channel id or `@username`
- `is_active`
- `description` optional
- `created_at`
- `updated_at`

The alias is what ChatGPT uses. Example: `channel="seo"`.

### TelegramPublishAudit

Fields:

- `public_id` UUID
- `channel`
- `action` (`test`, `publish`)
- `status` (`success`, `failed`)
- `telegram_message_id` nullable
- `content_preview` bounded preview only
- `content_sha256` for correlation without storing duplicate full payloads in audit metadata
- `error_code` nullable
- `error_message` sanitized and bounded
- `actor_principal`
- `created_at`

Full publish content does not need to be duplicated into the audit row if application logs or future content history provide it. Phase 1 should minimize sensitive data retention.

## Control Plane API

Admin/web endpoints:

- `GET /api/control/v1/telegram/status`
- `PUT /api/control/v1/telegram/bot-credential`
- `GET /api/control/v1/telegram/channels`
- `POST /api/control/v1/telegram/channels`
- `PATCH /api/control/v1/telegram/channels/{uuid}`
- `POST /api/control/v1/telegram/channels/{uuid}/test`
- `GET /api/control/v1/telegram/audit`

MCP/service endpoint:

- `POST /api/control/v1/telegram/publish`

Publish request:

```json
{
  "channel": "seo",
  "text": "...",
  "disable_web_page_preview": false
}
```

The API resolves the alias server-side, validates that the channel and bot are active, sends to Telegram, and returns a normalized result.

## MCP Tool Surface

Phase 1 exposes only three tools:

### `telegram_list_channels`

Read-only. Returns active channel aliases and display names. It does not expose bot credentials.

### `telegram_test_channel`

Write action. Sends a short fixed diagnostic message or uses Telegram capability checks to verify posting works. Requires a channel alias.

### `telegram_publish_message`

Write action.

Inputs:

- `channel`: channel alias
- `text`: required message body
- `disable_web_page_preview`: optional boolean

Behavior:

- Reject unknown or inactive aliases.
- Reject empty content.
- Enforce Telegram message size handling by safe chunking when needed.
- Preserve chunk order.
- Return the created Telegram message id(s).
- Record one audit event for the logical publish operation.

No arbitrary Telegram API method passthrough is exposed.

## Telegram Service

Use a small server-side Telegram client built on direct HTTPS Bot API calls or a lightweight Python client library. Prefer direct, explicit API calls for the small Phase 1 surface.

Responsibilities:

- `getMe` / credential validation
- channel test
- `sendMessage`
- safe message chunking
- error normalization
- timeouts and bounded retries for transient network failures only

The service must not log the bot token or authorization-bearing URLs.

## Admin UI

Public hostname: `bot.digitalafarin.ir`.

Phase 1 pages/components:

- Status card: bot configured, Telegram reachable, MCP status.
- Bot settings: replace/update bot token; never display existing token.
- Channels table: alias, name, chat id, active state, last test result.
- Add/edit channel form.
- Test button per channel.
- Recent audit table.

Keep the UI intentionally simple and consistent with the existing platform admin. No visual page builder or complex role system is required.

## Authentication and Security

- `bot.digitalafarin.ir` is HTTPS-only behind Nginx.
- Phase 1 reuses the existing Basic Auth deployment pattern for browser access.
- Next.js uses a dedicated service-principal credential stored only in its server runtime.
- Telegram MCP uses its own write-scoped service principal.
- Existing VPS MCP credential is never reused.
- Telegram bot token is encrypted at rest and never exposed to browser JS, MCP clients, logs, Git, issue trackers, or API responses.
- MCP binds to localhost only.
- Secure MCP Tunnel is the only external path from ChatGPT to the local Telegram MCP.
- Publish API accepts only known aliases from the database.
- No shell execution, URL fetching, arbitrary HTTP proxying, or generic Telegram method execution is part of this feature.

## Domain and Deployment

Production target:

- Admin: `https://bot.digitalafarin.ir`
- Telegram MCP: localhost-only dedicated port, selected to avoid existing `3060` VPS MCP.
- Django API remains on the existing local control-plane listener.

Nginx gets a dedicated vhost for `bot.digitalafarin.ir` and proxies to the existing Next.js web service or a bot-specific route on that service. Prefer reusing the existing Next.js process unless isolation or routing constraints discovered during implementation require a second web process.

A dedicated Telegram MCP systemd service and Secure MCP Tunnel service are added. Secrets live under `/etc/digitalafarin-platform/` with root/service-readable permissions.

## Error Handling

Normalize failures into actionable categories:

- bot credential missing/invalid
- channel unknown/inactive
- bot not an admin / insufficient Telegram rights
- channel not found
- Telegram rate limit
- Telegram/network timeout
- invalid message content
- internal configuration error

API and MCP responses return safe summaries. Raw upstream responses are not exposed when they may contain sensitive values.

## Testing

### Django

- model validation and unique alias tests
- encrypted token round-trip without plaintext persistence
- API authorization tests
- channel CRUD tests
- publish success/failure tests with mocked Telegram API
- audit event tests

### MCP

- tool registration
- channel listing
- publish request normalization
- unknown channel failure
- upstream API failure mapping

### Web

- status render
- channel list render
- add/edit validation
- token form does not hydrate/reveal existing secret
- test-channel action state

### Deployment verification

- Django checks/migrations
- backend tests
- MCP tests
- Next.js tests/lint/build
- systemd units active
- Nginx config test
- HTTPS reachable with auth
- Telegram test post succeeds
- MCP tunnel doctor/handshake succeeds
- live ChatGPT tool invocation succeeds when account/tool permissions allow write actions

## Non-Goals for Phase 1

- Receiving Telegram messages
- Telegram webhook ingestion
- OpenAI API calls from the server
- AI-generated content inside the server
- scheduled publishing
- photo/video/document publishing
- editing/deleting existing Telegram posts
- multi-user RBAC beyond existing protected admin access
- automatic cross-posting

These can be added later without changing the core channel/publisher abstraction.

## Acceptance Criteria

The feature is complete when:

1. An administrator can configure a bot token and multiple channel aliases from `bot.digitalafarin.ir`.
2. A channel can be tested from the UI and the result is audited.
3. ChatGPT can discover active channel aliases through the Telegram MCP.
4. ChatGPT can invoke `telegram_publish_message` for a selected alias.
5. The message appears in the intended Telegram channel.
6. No Telegram secret is present in Git, browser output, MCP output, or normal logs.
7. Existing VPS MCP behavior remains unchanged and read-only.
8. Backend, MCP, and web acceptance tests pass before deployment is claimed complete.
