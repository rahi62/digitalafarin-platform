#!/usr/bin/env bash
set -euo pipefail

PROJECT_SLUG="cafino"
PROJECT_NAME="Cafino"
DOMAIN="cafeno.digitalafarin.ir"
AGENT_ENV="/etc/digitalafarin-platform/agent.env"
MCP_ENV="/etc/digitalafarin-platform/mcp.env"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root."
  exit 1
fi

for unit in cafino-backend.service cafino-frontend.service cafino-worker.service cafino-beat.service cafino-backup.service; do
  systemctl status "$unit" --no-pager >/dev/null 2>&1 || true
  if ! systemctl list-unit-files "$unit" --no-legend 2>/dev/null | grep -q "^$unit"; then
    echo "Missing unit: $unit"
    exit 1
  fi
done

python3 - "$AGENT_ENV" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text() if path.exists() else ""
key = "AGENT_SERVICE_PREFIXES"
lines = text.splitlines()
found = False
out = []
for line in lines:
    if line.startswith(key + "="):
        found = True
        value = line.split("=", 1)[1].strip().strip('"').strip("'")
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if "cafino-" not in parts:
            parts.append("cafino-")
        out.append(f"{key}={','.join(parts)}")
    else:
        out.append(line)
if not found:
    out.append(f"{key}=digitalafarin-,oily-,cafino-")
path.write_text("\n".join(out).rstrip() + "\n")
PY

systemctl restart digitalafarin-platform-agent.service

set -a
source "$MCP_ENV"
set +a
API="${CONTROL_PLANE_URL:-http://127.0.0.1:9750}"
TOKEN="${CONTROL_PLANE_TOKEN:?CONTROL_PLANE_TOKEN is required in $MCP_ENV}"

api_get() {
  curl -fsS -H "Authorization: Bearer $TOKEN" "$API$1"
}
api_post() {
  local path="$1"; shift
  curl -fsS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" --data "$1" "$API$path"
}
api_put() {
  local path="$1"; shift
  curl -fsS -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" --data "$1" "$API$path"
}

SERVER_JSON="$(api_get /api/control/v1/servers/default/)"
SERVER_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$SERVER_JSON")"

for _ in $(seq 1 20); do
  SERVICES_JSON="$(api_get "/api/control/v1/servers/$SERVER_ID/services/")"
  if python3 -c 'import json,sys; print(any(x["unit_name"]=="cafino-backend.service" for x in json.load(sys.stdin)["items"]))' <<<"$SERVICES_JSON" | grep -q True; then
    break
  fi
  sleep 2
done

if ! python3 -c 'import json,sys; raise SystemExit(0 if any(x["unit_name"]=="cafino-backend.service" for x in json.load(sys.stdin)["items"]) else 1)' <<<"$SERVICES_JSON"; then
  echo "Cafino units are still missing from Agent inventory."
  exit 1
fi

PROJECTS_JSON="$(api_get /api/control/v1/projects/)"
PROJECT_ID="$(python3 -c 'import json,sys; slug=sys.argv[1]; print(next((x["id"] for x in json.load(sys.stdin)["items"] if x["slug"]==slug), ""))' "$PROJECT_SLUG" <<<"$PROJECTS_JSON")"
if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_JSON="$(api_post /api/control/v1/projects/ "{\"name\":\"$PROJECT_NAME\",\"slug\":\"$PROJECT_SLUG\"}")"
  PROJECT_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$PROJECT_JSON")"
fi

project_json() { api_get "/api/control/v1/projects/$PROJECT_ID/"; }

adopt_if_missing() {
  local name="$1" unit="$2"
  local current
  current="$(project_json)"
  local existing
  existing="$(python3 -c 'import json,sys; name,unit=sys.argv[1:3]; print(next((x["id"] for x in json.load(sys.stdin).get("services",[]) if x.get("name")==name or x.get("unit_name")==unit), ""))' "$name" "$unit" <<<"$current")"
  if [[ -n "$existing" ]]; then
    printf '%s' "$existing"
    return
  fi
  local body
  body="$(printf '{"server_id":"%s","unit_name":"%s","name":"%s"}' "$SERVER_ID" "$unit" "$name")"
  api_post "/api/control/v1/projects/$PROJECT_ID/services/adopt/" "$body"     | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
}

BACKEND_ID="$(adopt_if_missing backend cafino-backend.service)"
FRONTEND_ID="$(adopt_if_missing frontend cafino-frontend.service)"
adopt_if_missing worker cafino-worker.service >/dev/null
adopt_if_missing beat cafino-beat.service >/dev/null
adopt_if_missing backup cafino-backup.service >/dev/null

extract_port() {
  local unit="$1"
  systemctl show "$unit" -p ExecStart --value     | python3 -c 'import re,sys; s=sys.stdin.read(); m=re.search(r"(?:--port(?:=|\s+)|--bind(?:=|\s+)(?:127\.0\.0\.1|0\.0\.0\.0):)(\d+)", s); print(m.group(1) if m else "")'
}

BACKEND_PORT="$(extract_port cafino-backend.service)"
FRONTEND_PORT="$(extract_port cafino-frontend.service)"

if [[ -n "$BACKEND_PORT" ]]; then
  api_put "/api/control/v1/services/$BACKEND_ID/deployment-configuration/" "$(printf '{"repository":"https://github.com/rahi62/coffino.git","branch":"main","root_directory":"backend","runtime":"python-django","service_port":%s,"install_configuration":{"requirements_file":"requirements.txt"},"build_configuration":{"migrate":true,"collectstatic":true,"gunicorn_module":"config.wsgi:application"}}' "$BACKEND_PORT")" >/dev/null
else
  echo "Warning: backend port could not be derived; backend adopted without deployment metadata."
fi

if [[ -n "$FRONTEND_PORT" ]]; then
  api_put "/api/control/v1/services/$FRONTEND_ID/deployment-configuration/" "$(printf '{"repository":"https://github.com/rahi62/coffino.git","branch":"main","root_directory":"frontend","runtime":"node-nextjs","service_port":%s,"install_configuration":{"package_manager":"npm","lockfile":"package-lock.json"},"build_configuration":{"build_script":"build"}}' "$FRONTEND_PORT")" >/dev/null
else
  echo "Warning: frontend port could not be derived; frontend adopted without deployment metadata."
fi

CURRENT="$(project_json)"
if ! python3 -c 'import json,sys; host=sys.argv[1]; raise SystemExit(0 if any(x.get("hostname")==host for x in json.load(sys.stdin).get("domains",[])) else 1)' "$DOMAIN" <<<"$CURRENT"; then
  api_post "/api/control/v1/projects/$PROJECT_ID/domains/" "$(printf '{"service_id":"%s","hostname":"%s","configure_nginx":false,"ssl_enabled":true}' "$FRONTEND_ID" "$DOMAIN")" >/dev/null
fi

echo "Cafino registration complete."
project_json | python3 -c 'import json,sys; d=json.load(sys.stdin); print("Project:", d["name"], d["id"]); [print("Service:", x["name"], x["unit_name"], x["lifecycle_state"], x.get("inventory_status")) for x in d.get("services",[])]; [print("Domain:", x["hostname"], x["status"], x.get("management_mode")) for x in d.get("domains",[])]'
