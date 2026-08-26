#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="digitalafarin-wordpress-mcp"
APP_DIR="/var/www/${APP_NAME}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root or via the restricted sudo rule." >&2
  exit 1
fi

test -f "/etc/${APP_NAME}.env"
test -f "${APP_DIR}/package-lock.json"

chown -R deploy:deploy "${APP_DIR}"
sudo -u deploy npm --prefix "${APP_DIR}" ci
sudo -u deploy npm --prefix "${APP_DIR}" run build
systemctl restart "${APP_NAME}.service"
curl --fail --silent --show-error "http://127.0.0.1:3030/health"
