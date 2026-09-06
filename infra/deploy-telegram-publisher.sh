#!/usr/bin/env bash
set -euo pipefail

ROOT="${DIGITALAFARIN_PLATFORM_ROOT:-/opt/digitalafarin-platform}"
API_ENV="/etc/digitalafarin-platform/api.env"
WEB_ENV="/etc/digitalafarin-platform/web.env"
MCP_ENV="/etc/digitalafarin-platform/telegram-mcp.env"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

for required in "$ROOT" "$API_ENV" "$WEB_ENV" "$MCP_ENV"; do
  if [[ ! -e "$required" ]]; then
    echo "Required path is missing: $required" >&2
    exit 1
  fi
done

if ! grep -q '^TELEGRAM_CREDENTIAL_ENCRYPTION_KEY=' "$API_ENV"; then
  echo "TELEGRAM_CREDENTIAL_ENCRYPTION_KEY is missing from $API_ENV" >&2
  exit 1
fi
if ! grep -q '^TELEGRAM_PLATFORM_API_TOKEN=' "$WEB_ENV"; then
  echo "TELEGRAM_PLATFORM_API_TOKEN is missing from $WEB_ENV" >&2
  exit 1
fi
if ! grep -q '^CONTROL_PLANE_TOKEN=' "$MCP_ENV"; then
  echo "CONTROL_PLANE_TOKEN is missing from $MCP_ENV" >&2
  exit 1
fi

cd "$ROOT/apps/api"
if [[ ! -x .venv/bin/python ]]; then
  echo "API virtualenv missing: $ROOT/apps/api/.venv" >&2
  exit 1
fi
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py check

cd "$ROOT/telegram-mcp"
if [[ ! -d .venv ]]; then
  python3.12 -m venv .venv
fi
.venv/bin/pip install -e .

cd "$ROOT/apps/web"
npm install
npm test
npm run lint
npm run build

install -m 0644 "$ROOT/infra/systemd/digitalafarin-telegram-mcp.service" /etc/systemd/system/digitalafarin-telegram-mcp.service
install -m 0644 "$ROOT/infra/systemd/digitalafarin-telegram-mcp-tunnel.service" /etc/systemd/system/digitalafarin-telegram-mcp-tunnel.service
systemctl daemon-reload

systemctl restart digitalafarin-platform-api.service
systemctl restart digitalafarin-platform-web.service
systemctl enable --now digitalafarin-telegram-mcp.service

if systemctl is-enabled --quiet digitalafarin-telegram-mcp-tunnel.service 2>/dev/null; then
  systemctl restart digitalafarin-telegram-mcp-tunnel.service
else
  echo "Telegram MCP tunnel is not enabled yet; configure and verify profile 'digitalafarin-telegram' first."
fi

if [[ -e /etc/nginx/sites-enabled/digitalafarin-bot ]]; then
  nginx -t
  systemctl reload nginx
else
  echo "Nginx bot vhost is not enabled yet; install it only after DNS and TLS are ready."
fi

systemctl --no-pager --full status digitalafarin-platform-api.service digitalafarin-platform-web.service digitalafarin-telegram-mcp.service || true

echo "Telegram publisher application deployment finished. Live Telegram/Tunnel verification is still required."
