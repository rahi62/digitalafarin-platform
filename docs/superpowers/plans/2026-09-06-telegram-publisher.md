# Telegram Publisher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure multi-channel Telegram publisher to DigitalAfarin Platform, manageable at `bot.digitalafarin.ir` and callable from ChatGPT through a dedicated MCP service.

**Architecture:** Keep Telegram write capability isolated from the existing read-only VPS MCP. Django owns encrypted bot credentials, channel configuration, publishing and audit; a separate localhost MCP calls only scoped Telegram control-plane endpoints; Next.js provides a small admin UI and never exposes service credentials to the browser.

**Tech Stack:** Django 5.2 / DRF, PostgreSQL, `cryptography` Fernet, `httpx`, MCP Python SDK, Next.js 16 / React 19, systemd, Nginx, OpenAI Secure MCP Tunnel.

**Spec:** `docs/superpowers/specs/2026-09-06-telegram-publisher-design.md`

## Global Constraints

- Existing VPS MCP stays read-only and unchanged in behavior.
- Telegram MCP binds to localhost only and uses a dedicated service principal.
- Telegram bot token is encrypted at rest and never returned by API/MCP or rendered into browser HTML.
- No arbitrary Telegram API passthrough, shell, URL fetcher, or generic HTTP proxy.
- Phase 1 supports text publishing, channel test/list, multi-channel aliases, admin CRUD and audit only.
- Production admin hostname is `https://bot.digitalafarin.ir` behind HTTPS + Basic Auth.

---

### Task 1: Django Telegram domain, encrypted credential and channel models

**Files:**
- Modify: `apps/api/control/models.py`
- Create: `apps/api/control/telegram_crypto.py`
- Create: `apps/api/control/migrations/0006_telegram_publisher.py`
- Modify: `apps/api/requirements.txt`
- Test: `apps/api/control/tests/test_telegram_models.py`

**Interfaces:**
- Produces: `TelegramBotCredential`, `TelegramChannel`, `TelegramPublishAudit`, `encrypt_bot_token(str)->str`, `decrypt_bot_token(str)->str`.

- [ ] Write tests asserting normalized unique channel aliases, encrypted token round-trip, and no plaintext token in ciphertext.
- [ ] Run Django tests and confirm the new tests fail because the models/helpers do not exist.
- [ ] Add `cryptography>=43,<47` and implement Fernet encryption from `TELEGRAM_CREDENTIAL_ENCRYPTION_KEY`.
- [ ] Add models with UUID public IDs, bounded audit data, stable lowercase alias validation and ordering.
- [ ] Add migration matching the model schema.
- [ ] Re-run model tests and Django system check.
- [ ] Commit the task.

### Task 2: Telegram client, scoped Control Plane APIs and auditing

**Files:**
- Create: `apps/api/control/telegram_client.py`
- Create: `apps/api/control/telegram_serializers.py`
- Create: `apps/api/control/telegram_views.py`
- Modify: `apps/api/control/control_urls.py`
- Modify: `apps/api/control/management/commands/create_service_principal.py`
- Test: `apps/api/control/tests/test_telegram_api.py`

**Interfaces:**
- Produces: `TelegramClient.validate_bot()`, `TelegramClient.send_message(chat_id,text,disable_web_page_preview=False)`, admin scopes `telegram:admin`, MCP scopes `telegram:read` and `telegram:publish`.
- API routes: `/api/control/v1/telegram/status/`, `/bot-credential/`, `/channels/`, `/channels/<uuid>/`, `/channels/<uuid>/test/`, `/audit/`, `/publish/`.

- [ ] Write API tests with mocked Telegram transport for credential replacement, channel CRUD, test post, list/audit and publish permission checks.
- [ ] Run tests and verify expected failures.
- [ ] Implement a small `httpx` Bot API client with timeout, normalized upstream errors and safe 4096-character chunking.
- [ ] Implement serializers and views using `ServicePrincipalAuthentication` plus exact scope checks.
- [ ] Ensure every test/publish produces a bounded audit row and raw Telegram responses/tokens are never persisted.
- [ ] Extend the service-principal management command with `--profile readonly|telegram-admin|telegram-mcp` while preserving current default behavior.
- [ ] Run backend tests and Django check.
- [ ] Commit the task.

### Task 3: Dedicated Telegram MCP

**Files:**
- Create: `telegram-mcp/pyproject.toml`
- Create: `telegram-mcp/digitalafarin_telegram_mcp/__init__.py`
- Create: `telegram-mcp/digitalafarin_telegram_mcp/config.py`
- Create: `telegram-mcp/digitalafarin_telegram_mcp/control_plane.py`
- Create: `telegram-mcp/digitalafarin_telegram_mcp/server.py`
- Create: `telegram-mcp/tests/test_server.py`

**Interfaces:**
- Produces tools: `telegram_list_channels`, `telegram_test_channel`, `telegram_publish_message`.
- Environment: `CONTROL_PLANE_URL`, `CONTROL_PLANE_TOKEN`, `TELEGRAM_MCP_HOST`, `TELEGRAM_MCP_PORT`, `TELEGRAM_MCP_PATH`.

- [ ] Write tool-registration and fake-client tests first.
- [ ] Run tests and confirm failure before implementation.
- [ ] Implement scoped Control Plane client and MCP server mirroring the existing VPS MCP transport pattern without importing/reusing VPS write paths.
- [ ] Include clear tool descriptions identifying test/publish as write actions and return normalized dictionaries only.
- [ ] Run Telegram MCP tests.
- [ ] Commit the task.

### Task 4: Next.js admin UI for `bot.digitalafarin.ir`

**Files:**
- Create: `apps/web/lib/telegram.ts`
- Create: `apps/web/lib/telegram.test.ts`
- Create: `apps/web/app/bot/actions.ts`
- Create: `apps/web/app/bot/page.tsx`
- Create: `apps/web/app/bot/bot-admin.tsx`
- Modify: `apps/web/app/globals.css`

**Interfaces:**
- Server-only API client functions: `getTelegramStatus`, `listTelegramChannels`, `listTelegramAudit`, `setTelegramCredential`, `createTelegramChannel`, `updateTelegramChannel`, `testTelegramChannel`.

- [ ] Write Node tests for payload normalization, alias validation helpers and ensuring the secret type is write-only.
- [ ] Run web tests and confirm initial failure.
- [ ] Implement server-only API client with GET/POST/PUT/PATCH requests using the existing `PLATFORM_API_URL` and `PLATFORM_API_TOKEN` pattern.
- [ ] Implement server actions with `revalidatePath('/bot')`; the browser submits the token but never receives an existing token value.
- [ ] Build a simple responsive page: status cards, replace-token form, add channel form, channel table with activate/deactivate/test controls, recent audit.
- [ ] Add minimal component-specific CSS while reusing existing visual language.
- [ ] Run `npm test`, `npm run lint`, and `npm run build`.
- [ ] Commit the task.

### Task 5: Production infrastructure and deployment documentation

**Files:**
- Modify: `.env.example`
- Create: `infra/systemd/digitalafarin-telegram-mcp.service`
- Create: `infra/systemd/digitalafarin-telegram-mcp-tunnel.service`
- Create: `infra/nginx/bot.conf.example`
- Create: `infra/deploy-telegram-publisher.sh`
- Modify: `README.md`

**Interfaces:**
- Local MCP endpoint: `127.0.0.1:3061/mcp`.
- Admin hostname: `bot.digitalafarin.ir`, proxying to existing Next.js `127.0.0.1:9751` route `/bot`.
- Root-managed env: `/etc/digitalafarin-platform/telegram-mcp.env`; API encryption key is added to API env.

- [ ] Add systemd units with hardening, dedicated `digitalafarin-mcp` user and no secrets embedded in unit files.
- [ ] Add Nginx host with Basic Auth, HTTPS placeholder paths and proxying `/` to the existing Next.js `/bot` route.
- [ ] Add an idempotent deployment helper that performs migrations/build/install/restart but does not invent DNS, bot token, tunnel credentials or TLS certificate.
- [ ] Document exact one-time production setup commands including key generation, service principals and tunnel profile.
- [ ] Validate shell syntax and review secret handling.
- [ ] Commit the task.

### Task 6: Final verification and integration

**Files:**
- Review all changed files.

- [ ] Run backend test suite and `python manage.py check`.
- [ ] Run Telegram MCP tests.
- [ ] Run web tests, ESLint and production build.
- [ ] Run `git diff --check` / equivalent whitespace review and verify no token-like secrets entered the branch.
- [ ] Open a PR from `feat/telegram-publisher` to `main` with verification evidence and deployment checklist.
- [ ] Do not claim live deployment until DNS, cert, server commands, bot token and Secure MCP Tunnel are actually configured and verified on the VPS.
