# Telegram Publisher Production Deployment

Target: `bot.digitalafarin.ir`

This procedure deploys the Telegram publisher added by `feat/telegram-publisher`. It deliberately keeps the Telegram write surface separate from the existing read-only VPS MCP.

## 0. Preconditions

- `bot.digitalafarin.ir` DNS points to the DigitalAfarin primary VPS.
- Repository is installed at `/opt/digitalafarin-platform`.
- Existing Platform API and Web services are healthy.
- `digitalafarin-mcp` Unix user already exists (the VPS MCP already uses it).
- `tunnel-client` is installed and the existing Secure MCP Tunnel setup is healthy.
- A Telegram bot has been created with BotFather. Do not store its token in Git or shell scripts.
- The Telegram bot is an administrator with permission to post messages in every target channel.

## 1. Update the repository

```bash
cd /opt/digitalafarin-platform
git fetch origin
git checkout main
git pull --ff-only origin main
```

Run this only after the feature PR has been merged.

## 2. Backend encryption key

The Telegram bot token is stored encrypted in Django. Generate the encryption key once:

```bash
cd /opt/digitalafarin-platform/apps/api
source .venv/bin/activate
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Add the resulting value to `/etc/digitalafarin-platform/api.env`:

```dotenv
TELEGRAM_CREDENTIAL_ENCRYPTION_KEY=<fernet-key>
```

Do not rotate this value without re-encrypting the stored bot credential first.

## 3. Create dedicated service principals

Create a web-admin identity:

```bash
cd /opt/digitalafarin-platform/apps/api
source .venv/bin/activate
python manage.py create_service_principal telegram-admin-web --profile telegram-admin
```

Put the one-time printed value in `/etc/digitalafarin-platform/web.env`:

```dotenv
TELEGRAM_PLATFORM_API_TOKEN=<telegram-admin-web credential>
```

Do not replace the existing `PLATFORM_API_TOKEN`; the existing Platform UI still needs its current read-only VPS principal.

Create the dedicated Telegram MCP identity:

```bash
python manage.py create_service_principal chatgpt-telegram-mcp --profile telegram-mcp
```

Create `/etc/digitalafarin-platform/telegram-mcp.env` without echoing the credential into logs:

```dotenv
CONTROL_PLANE_URL=http://127.0.0.1:9750
CONTROL_PLANE_TOKEN=<chatgpt-telegram-mcp credential>
TELEGRAM_MCP_HOST=127.0.0.1
TELEGRAM_MCP_PORT=3061
TELEGRAM_MCP_PATH=/mcp
```

Protect it:

```bash
sudo chown root:digitalafarin-mcp /etc/digitalafarin-platform/telegram-mcp.env
sudo chmod 640 /etc/digitalafarin-platform/telegram-mcp.env
```

## 4. Run application deployment

The helper validates required env files before mutating services:

```bash
cd /opt/digitalafarin-platform
sudo bash infra/deploy-telegram-publisher.sh
```

It installs backend dependencies, migrates Django, runs Django checks, installs the Telegram MCP, tests/lints/builds Next.js, installs the new systemd units, and restarts the application services. It does not invent DNS, TLS, Telegram tokens, or tunnel credentials.

Verify the local MCP:

```bash
sudo systemctl status digitalafarin-telegram-mcp --no-pager
ss -ltnp | grep ':3061'
```

Port 3061 must bind to `127.0.0.1`, not a public interface.

## 5. Basic Auth for `bot.digitalafarin.ir`

Create a separate password file:

```bash
sudo apt-get install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd-digitalafarin-bot rahi
sudo chown root:www-data /etc/nginx/.htpasswd-digitalafarin-bot
sudo chmod 640 /etc/nginx/.htpasswd-digitalafarin-bot
```

## 6. Bootstrap HTTP and obtain TLS

Before the certificate exists, use a temporary HTTP-only vhost:

```bash
sudo tee /etc/nginx/sites-available/digitalafarin-bot-bootstrap >/dev/null <<'EOF'
server {
    listen 80;
    server_name bot.digitalafarin.ir;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 404; }
}
EOF
sudo ln -sfn /etc/nginx/sites-available/digitalafarin-bot-bootstrap /etc/nginx/sites-enabled/digitalafarin-bot-bootstrap
sudo nginx -t
sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/html -d bot.digitalafarin.ir
```

After certificate issuance, install the committed HTTPS vhost:

```bash
sudo cp /opt/digitalafarin-platform/infra/nginx/bot.conf.example /etc/nginx/sites-available/digitalafarin-bot
sudo ln -sfn /etc/nginx/sites-available/digitalafarin-bot /etc/nginx/sites-enabled/digitalafarin-bot
sudo rm -f /etc/nginx/sites-enabled/digitalafarin-bot-bootstrap
sudo nginx -t
sudo systemctl reload nginx
```

Verify unauthenticated requests are protected and authenticated requests reach `/bot`.

## 7. Configure the bot token and channels

Open:

`https://bot.digitalafarin.ir`

Then:

1. Enter the BotFather token in **Bot Token جدید**. The server validates it with Telegram before encrypting it.
2. Add each channel using a stable alias such as `seo`, `ai`, or `digitalafarin`.
3. Use either the channel `@username` or numeric channel chat ID (`-100...`).
4. Press **ارسال پیام تست** for every channel.
5. Confirm the diagnostic message appears in the intended channel and the UI audit row is `success`.

The existing token is intentionally never rendered back into the page.

## 8. Configure the Secure MCP Tunnel

Create a new tunnel profile named `digitalafarin-telegram` using the same account/setup mechanism already used for `digitalafarin-vps`, but target the new local endpoint:

```text
http://127.0.0.1:3061/mcp
```

Do not reuse or overwrite the `digitalafarin-vps` profile.

Verify the profile as the service account:

```bash
sudo -u digitalafarin-mcp tunnel-client doctor --profile digitalafarin-telegram --explain
```

The committed systemd unit expects the tunnel client at `/usr/local/bin/tunnel-client`. Confirm the real path first:

```bash
command -v tunnel-client
```

If the binary lives elsewhere, update only `ExecStart` in `/etc/systemd/system/digitalafarin-telegram-mcp-tunnel.service`.

After `doctor` passes:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now digitalafarin-telegram-mcp-tunnel.service
sudo systemctl status digitalafarin-telegram-mcp-tunnel.service --no-pager
```

## 9. ChatGPT connector acceptance check

The connector should expose exactly these tools:

- `telegram_list_channels`
- `telegram_test_channel`
- `telegram_publish_message`

Acceptance sequence:

1. Ask ChatGPT to list Telegram channels.
2. Ask it to test one known alias.
3. Confirm the test message appears.
4. Ask it to publish a short text to that alias.
5. Confirm the Telegram message ID(s) are returned and the message appears in the intended channel.
6. Confirm the publish appears in the admin audit table.

A publish must not be reported as successful unless the MCP response contains `ok: true`.

## 10. Production health checks

```bash
sudo systemctl status digitalafarin-platform-api digitalafarin-platform-web digitalafarin-telegram-mcp digitalafarin-telegram-mcp-tunnel --no-pager
sudo nginx -t
curl -I https://bot.digitalafarin.ir
```

Expected unauthenticated response for the admin host is `401 Unauthorized` because Basic Auth is required.

Never paste Telegram bot tokens, service-principal credentials, encryption keys, or tunnel credentials into GitHub issues, PRs, ChatGPT, screenshots, or ordinary logs.
