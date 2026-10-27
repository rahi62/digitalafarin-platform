#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/var/www/digitalafarin-agency-mcp"
ENV_FILE="/etc/digitalafarin-agency-mcp.env"
SERVICE_FILE="/etc/systemd/system/digitalafarin-agency-mcp.service"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install-server.sh" >&2
  exit 1
fi

if ! id deploy >/dev/null 2>&1; then
  echo "deploy user does not exist" >&2
  exit 1
fi

if [[ ! -f "$SOURCE_DIR/package.json" ]]; then
  echo "package.json not found in $SOURCE_DIR" >&2
  exit 1
fi

# Supports a repository cloned directly to APP_DIR (preferred) or another checkout path.
if [[ "$SOURCE_DIR" != "$APP_DIR" ]]; then
  mkdir -p "$APP_DIR/data"
  find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name data -exec rm -rf -- {} +
  cp -a "$SOURCE_DIR"/. "$APP_DIR"/
fi

mkdir -p "$APP_DIR/data"
chown -R deploy:deploy "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  GENERATED_CSRF_SECRET="$(openssl rand -hex 32)"
  cat > "$ENV_FILE" <<ENV
HOST=127.0.0.1
PORT=3050
ALLOWED_ORIGINS=https://chatgpt.com
BEARER_TOKEN=
DATA_FILE=/var/www/digitalafarin-agency-mcp/data/agency.json
STORE_DRIVER=json
DATABASE_URL=postgresql://digitalafarin_agency:change-me@127.0.0.1:5432/digitalafarin_agency
SESSION_COOKIE_NAME=digitalafarin_agency_session
SESSION_TTL_HOURS=168
ADMIN_ORIGIN=https://agency.digitalafarin.ir
CSRF_SECRET=$GENERATED_CSRF_SECRET
ENV
  chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE with JSON persistence. Configure DATABASE_URL before PostgreSQL cutover."
  echo "MCP remains bound to localhost; Secure MCP Tunnel provides external access."
else
  echo "Keeping existing $ENV_FILE"
fi

sudo -u deploy bash -lc "cd '$APP_DIR' && npm install --no-audit --no-fund && npm run check && npm test && npm run build"
install -m 0644 "$APP_DIR/deploy/digitalafarin-agency-mcp.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable --now digitalafarin-agency-mcp.service
sleep 1
curl --fail --silent --show-error http://127.0.0.1:3050/health
echo
systemctl --no-pager --full status digitalafarin-agency-mcp.service | sed -n '1,20p'
