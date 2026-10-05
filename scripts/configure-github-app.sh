#!/usr/bin/env bash
set -euo pipefail

APP_ID="${1:-}"
APP_SLUG="${2:-}"
PRIVATE_KEY_FILE="${3:-}"
API_ENV="/etc/digitalafarin-platform/api.env"

usage() {
  echo "Usage: sudo bash scripts/configure-github-app.sh <app-id> <app-slug> <private-key.pem>"
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root."
  exit 1
fi
if [[ -z "$APP_ID" || -z "$APP_SLUG" || -z "$PRIVATE_KEY_FILE" ]]; then
  usage
  exit 2
fi
if ! [[ "$APP_ID" =~ ^[0-9]+$ ]]; then
  echo "Invalid GitHub App ID."
  exit 2
fi
if ! [[ "$APP_SLUG" =~ ^[A-Za-z0-9-]+$ ]]; then
  echo "Invalid GitHub App slug."
  exit 2
fi
if [[ ! -r "$PRIVATE_KEY_FILE" ]]; then
  echo "Private key file is not readable."
  exit 2
fi

python3 - "$API_ENV" "$APP_ID" "$APP_SLUG" "$PRIVATE_KEY_FILE" <<'PY'
from pathlib import Path
import secrets
import sys

env_path = Path(sys.argv[1])
app_id = sys.argv[2]
slug = sys.argv[3]
key_path = Path(sys.argv[4])

key = key_path.read_text(encoding="utf-8").strip()
if "BEGIN" not in key or "PRIVATE KEY" not in key or "END" not in key:
    raise SystemExit("Private key file does not look like a PEM private key.")

escaped = key.replace("\\", "\\\\").replace("\n", "\\n")
existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
values = {
    "GITHUB_APP_ID": app_id,
    "GITHUB_APP_SLUG": slug,
    "GITHUB_APP_PRIVATE_KEY": escaped,
}
current = {}
for line in existing.splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        current[k.strip()] = v
webhook = current.get("GITHUB_APP_WEBHOOK_SECRET", "").strip().strip('"').strip("'")
if not webhook:
    webhook = secrets.token_hex(32)
values["GITHUB_APP_WEBHOOK_SECRET"] = webhook

out = []
seen = set()
for line in existing.splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key_name = line.split("=", 1)[0].strip()
        if key_name in values:
            out.append(f"{key_name}={values[key_name]}")
            seen.add(key_name)
            continue
    out.append(line)
for key_name, value in values.items():
    if key_name not in seen:
        out.append(f"{key_name}={value}")
env_path.parent.mkdir(parents=True, exist_ok=True)
env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY

chown root:www-data "$API_ENV"
chmod 0640 "$API_ENV"

systemctl restart digitalafarin-platform-api.service

for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:9750/health/ >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS --max-time 5 http://127.0.0.1:9750/health/ >/dev/null || {
  echo "Platform API did not become healthy."
  exit 3
}

bash /opt/digitalafarin-platform/scripts/diagnose-github-source.sh   https://github.com/rahi62/coffino.git || true

echo
echo "GitHub App credentials installed without printing secret values."
echo "Private key source file can now be removed from the VPS after validation."
