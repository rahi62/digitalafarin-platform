#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/digitalafarin-agency-mcp}"
ADMIN_DIR="$APP_DIR/admin"
SERVICE_FILE="/etc/systemd/system/digitalafarin-agency-admin.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install-admin.sh" >&2
  exit 1
fi

if ! id deploy >/dev/null 2>&1; then
  echo "deploy user does not exist" >&2
  exit 1
fi

if [[ ! -f "$ADMIN_DIR/package.json" ]]; then
  echo "Admin package not found at $ADMIN_DIR. Deploy the repository code first." >&2
  exit 1
fi

if [[ ! -f "$APP_DIR/deploy/digitalafarin-agency-admin.service" ]]; then
  echo "Admin systemd unit template is missing from deployed repository." >&2
  exit 1
fi

chown -R deploy:deploy "$ADMIN_DIR"

sudo -u deploy bash -lc "cd '$ADMIN_DIR' && npm install --no-audit --no-fund && npm run check && npm run check:rtl && npm run test:rtl && npm run build"
mkdir -p "$ADMIN_DIR/.next/cache"
chown -R deploy:deploy "$ADMIN_DIR/.next/cache"

install -m 0644 "$APP_DIR/deploy/digitalafarin-agency-admin.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable --now digitalafarin-agency-admin.service
sleep 2

curl --fail --silent --show-error http://127.0.0.1:3061/login >/dev/null
systemctl --no-pager --full status digitalafarin-agency-admin.service | sed -n '1,20p'
echo "Agency Control Center admin is healthy on http://127.0.0.1:3061"
