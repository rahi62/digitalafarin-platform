#!/usr/bin/env bash
set -euo pipefail

TARGET_COMMIT="${1:-01803d9340b8e1761f2062992cd3159198ae2513}"
PROJECT_SLUG="cafino"
SERVICE_NAME="frontend"
UNIT_NAME="cafino-frontend.service"
DOMAIN="cafeno.digitalafarin.ir"
MCP_ENV="/etc/digitalafarin-platform/mcp.env"
HELPER_DROPIN_DIR="/etc/systemd/system/digitalafarin-platform-takeover-helper.service.d"
HELPER_DROPIN="$HELPER_DROPIN_DIR/30-cafino.conf"
SOURCE_PARENT="/srv/digitalafarin/apps/.sources"
SOURCE_REPO="$SOURCE_PARENT/coffino"
MANAGED_REMOTE="https://github.com/rahi62/coffino.git"
COMPAT_DROPIN_DIR="/etc/systemd/system/${UNIT_NAME}.d"
COMPAT_DROPIN="$COMPAT_DROPIN_DIR/20-cafino-relative-exec.conf"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root."
  exit 1
fi

if ! [[ "$TARGET_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
  echo "TARGET_COMMIT must be an exact lowercase 40-character Git SHA."
  exit 1
fi

for cmd in git curl python3 systemctl nginx sed awk grep runuser id; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing command: $cmd"; exit 1; }
done

set -a
source "$MCP_ENV"
set +a
API="${CONTROL_PLANE_URL:-http://127.0.0.1:9750}"
TOKEN="${CONTROL_PLANE_TOKEN:?CONTROL_PLANE_TOKEN is required}"

api_get() {
  curl -fsS -H "Authorization: Bearer $TOKEN" "$API$1"
}
api_post() {
  local path="$1" body="$2"
  curl -fsS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" --data "$body" "$API$path"
}
api_put() {
  local path="$1" body="$2"
  curl -fsS -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" --data "$body" "$API$path"
}

PROJECTS="$(api_get /api/control/v1/projects/)"
PROJECT_ID="$(python3 -c 'import json,sys; slug=sys.argv[1]; print(next((x["id"] for x in json.load(sys.stdin)["items"] if x["slug"]==slug), ""))' "$PROJECT_SLUG" <<<"$PROJECTS")"
[[ -n "$PROJECT_ID" ]] || { echo "Cafino project not found."; exit 1; }

PROJECT="$(api_get "/api/control/v1/projects/$PROJECT_ID/")"
SERVICE_ID="$(python3 -c 'import json,sys; name=sys.argv[1]; print(next((x["id"] for x in json.load(sys.stdin).get("services",[]) if x["name"]==name), ""))' "$SERVICE_NAME" <<<"$PROJECT")"
[[ -n "$SERVICE_ID" ]] || { echo "Cafino frontend service not found."; exit 1; }

WORKDIR="$(systemctl show "$UNIT_NAME" -p WorkingDirectory --value)"
[[ -d "$WORKDIR" ]] || { echo "Frontend WorkingDirectory is unavailable: $WORKDIR"; exit 1; }

SERVICE_USER="$(systemctl show "$UNIT_NAME" -p User --value)"
SERVICE_GROUP="$(systemctl show "$UNIT_NAME" -p Group --value)"
[[ -n "$SERVICE_USER" && "$SERVICE_USER" != "root" ]] || {
  echo "Unsafe frontend service user: ${SERVICE_USER:-root/default}"
  echo "The frontend unit must run as a dedicated non-root user before controlled takeover."
  exit 1
}
[[ -n "$SERVICE_GROUP" ]] || SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

EXEC_START="$(systemctl show "$UNIT_NAME" -p ExecStart --value)"
normalize_standalone_execstart() {
  local expected="$WORKDIR/.next/standalone/server.js"
  if [[ "$EXEC_START" != *"$expected"* ]]; then
    return 0
  fi

  if [[ "$EXEC_START" != *"path=/usr/bin/node"* ]]; then
    echo "Refusing takeover: absolute runtime path is not the supported Node standalone shape."
    echo "ExecStart=$EXEC_START"
    exit 1
  fi

  echo "Normalizing Cafino frontend ExecStart to release-relative Next.js standalone path..."
  mkdir -p "$COMPAT_DROPIN_DIR"
  cat > "$COMPAT_DROPIN" <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/node .next/standalone/server.js
EOF
  chmod 0644 "$COMPAT_DROPIN"
  systemctl daemon-reload
  systemctl restart "$UNIT_NAME"

  for _ in $(seq 1 30); do
    if systemctl is-active --quiet "$UNIT_NAME" && curl -kfsS --max-time 5 "https://$DOMAIN/" >/dev/null; then
      break
    fi
    sleep 2
  done
  if ! systemctl is-active --quiet "$UNIT_NAME" || ! curl -kfsS --max-time 10 "https://$DOMAIN/" >/dev/null; then
    echo "Compatibility restart failed; removing relative ExecStart drop-in and restoring original service."
    rm -f "$COMPAT_DROPIN"
    rmdir "$COMPAT_DROPIN_DIR" 2>/dev/null || true
    systemctl daemon-reload
    systemctl restart "$UNIT_NAME"
    exit 1
  fi

  EXEC_START="$(systemctl show "$UNIT_NAME" -p ExecStart --value)"
  echo "Frontend ExecStart normalized successfully."
}

normalize_standalone_execstart

if [[ "$EXEC_START" == *"$WORKDIR/"* ]]; then
  echo "Refusing takeover: ExecStart still contains an absolute path inside the old runtime directory."
  echo "ExecStart=$EXEC_START"
  exit 1
fi

prepare_source_binding() {
  mkdir -p "$SOURCE_PARENT"
  rm -rf "$SOURCE_REPO"
  mkdir -p "$SOURCE_REPO"
  chown "$SERVICE_USER:$SERVICE_GROUP" "$SOURCE_REPO"
  chmod 0750 "$SOURCE_REPO"
}

prepare_source_binding

BACKEND_PORT="$(python3 -c 'import json,sys; print(next((str(x.get("service_port") or "") for x in json.load(sys.stdin).get("services",[]) if x["name"]=="backend"), ""))' <<<"$PROJECT")"

port_from_env() {
  systemctl show "$UNIT_NAME" -p Environment --value     | tr ' ' '\n'     | sed -n 's/^PORT=\([0-9][0-9]*\)$/\1/p'     | head -1
}

port_from_exec() {
  local raw
  raw="$(systemctl show "$UNIT_NAME" -p ExecStart --value)"
  python3 -c 'import re,sys; s=sys.stdin.read(); patterns=[r"--port(?:=|\\s+)(\\d+)",r"(?:^|\\s)-p(?:=|\\s+)(\\d+)",r"127\\.0\\.0\\.1:(\\d+)",r"0\\.0\\.0\\.0:(\\d+)"]; print(next((m.group(1) for p in patterns if (m:=re.search(p,s))), ""))' <<<"$raw"
}

port_from_nginx() {
  local conf ports
  conf="$(nginx -T 2>/dev/null || true)"
  ports="$(python3 -c 'import re,sys; domain=sys.argv[1]; lines=sys.stdin.read().splitlines(); active=False; depth=0; seen=False; out=[]
for line in lines:
    if not active and re.search(r"\\bserver\\s*\\{", line):
        active=True; depth=line.count("{")-line.count("}"); seen=False; block=[]; continue
    if active:
        block.append(line); depth += line.count("{")-line.count("}")
        if re.search(r"server_name\\s+[^;]*\\b"+re.escape(domain)+r"\\b", line): seen=True
        if depth<=0:
            if seen:
                text="\\n".join(block)
                out.extend(re.findall(r"proxy_pass\\s+http://(?:127\\.0\\.0\\.1|localhost):(\\d+)", text))
            active=False
print("\\n".join(out))' "$DOMAIN" <<<"$conf")"
  while read -r p; do
    [[ -n "$p" ]] || continue
    if [[ -z "$BACKEND_PORT" || "$p" != "$BACKEND_PORT" ]]; then
      echo "$p"
      return 0
    fi
  done <<<"$ports"
}

FRONTEND_PORT="$(port_from_env || true)"
[[ -n "$FRONTEND_PORT" ]] || FRONTEND_PORT="$(port_from_exec || true)"
[[ -n "$FRONTEND_PORT" ]] || FRONTEND_PORT="$(port_from_nginx || true)"
[[ "$FRONTEND_PORT" =~ ^[0-9]+$ ]] || { echo "Could not derive frontend port."; exit 1; }

echo "Runtime working directory: $WORKDIR"
echo "Takeover source transport: GitHub App bundle (private repo)"
echo "Trusted local fallback binding: $SOURCE_REPO"
echo "Frontend port: $FRONTEND_PORT"
echo "Service user/group: $SERVICE_USER:$SERVICE_GROUP"
echo "Target commit: $TARGET_COMMIT"

CONFIG_BODY="$(printf '{"repository":"%s","branch":"main","root_directory":"frontend","runtime":"node-nextjs","service_port":%s,"install_configuration":{"package_manager":"npm","lockfile":"package-lock.json"},"build_configuration":{"build_script":"build"}}' "$MANAGED_REMOTE" "$FRONTEND_PORT")"
api_put "/api/control/v1/services/$SERVICE_ID/deployment-configuration/" "$CONFIG_BODY" >/dev/null

EFFECTIVE_ENV="$(systemctl show digitalafarin-platform-takeover-helper.service -p Environment --value)"
CURRENT_BINDINGS="$(tr ' ' '\n' <<<"$EFFECTIVE_ENV" | sed -n 's/^DIGITALAFARIN_TAKEOVER_ALLOWED_BINDINGS=//p' | head -1)"
CURRENT_SOURCES="$(tr ' ' '\n' <<<"$EFFECTIVE_ENV" | sed -n 's/^DIGITALAFARIN_TAKEOVER_SOURCE_REPOSITORIES=//p' | head -1)"
CURRENT_MANAGED="$(tr ' ' '\n' <<<"$EFFECTIVE_ENV" | sed -n 's/^DIGITALAFARIN_MANAGED_REPOSITORIES=//p' | head -1)"

BINDING="cafino|frontend|cafino-frontend.service"
SOURCE="$BINDING|$SOURCE_REPO"
MANAGED="$BINDING|$MANAGED_REMOTE"

append_csv() {
  local current="$1" item="$2"
  if [[ ",$current," == *",$item,"* ]]; then
    printf '%s' "$current"
  elif [[ -n "$current" ]]; then
    printf '%s,%s' "$current" "$item"
  else
    printf '%s' "$item"
  fi
}

NEW_BINDINGS="$(append_csv "$CURRENT_BINDINGS" "$BINDING")"
NEW_SOURCES="$(append_csv "$CURRENT_SOURCES" "$SOURCE")"
NEW_MANAGED="$(append_csv "$CURRENT_MANAGED" "$MANAGED")"

for value in "$NEW_BINDINGS" "$NEW_SOURCES" "$NEW_MANAGED"; do
  if [[ "$value" == *'"'* || "$value" == *$'\n'* ]]; then
    echo "Unsafe helper environment value."
    exit 1
  fi
done

mkdir -p "$HELPER_DROPIN_DIR"
cat > "$HELPER_DROPIN" <<EOF
[Service]
Environment="DIGITALAFARIN_TAKEOVER_ALLOWED_BINDINGS=$NEW_BINDINGS"
Environment="DIGITALAFARIN_TAKEOVER_SOURCE_REPOSITORIES=$NEW_SOURCES"
Environment="DIGITALAFARIN_MANAGED_REPOSITORIES=$NEW_MANAGED"
EOF

systemctl daemon-reload
systemctl restart digitalafarin-platform-takeover-helper.service
systemctl is-active --quiet digitalafarin-platform-takeover-helper.service

TAKEOVER="$(api_post "/api/control/v1/services/$SERVICE_ID/takeovers/" "$(printf '{"commit":"%s"}' "$TARGET_COMMIT")")"
TAKEOVER_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$TAKEOVER")"
echo "Takeover: $TAKEOVER_ID"

for _ in $(seq 1 300); do
  STATE_JSON="$(api_get "/api/control/v1/takeovers/$TAKEOVER_ID/")"
  STATE="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["state"])' <<<"$STATE_JSON")"
  case "$STATE" in
    prepared)
      break
      ;;
    failed|rolled_back|rollback_failed|canceled)
      python3 -c 'import json,sys; d=json.load(sys.stdin); print("Takeover prepare failed:", d.get("failure_code"), d.get("failure_message"))' <<<"$STATE_JSON"
      exit 1
      ;;
  esac
  sleep 2
done

STATE_JSON="$(api_get "/api/control/v1/takeovers/$TAKEOVER_ID/")"
STATE="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["state"])' <<<"$STATE_JSON")"
[[ "$STATE" == "prepared" ]] || { echo "Takeover did not reach prepared state."; exit 1; }

api_post "/api/control/v1/takeovers/$TAKEOVER_ID/activate/" '{}' >/dev/null

for _ in $(seq 1 120); do
  STATE_JSON="$(api_get "/api/control/v1/takeovers/$TAKEOVER_ID/")"
  STATE="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["state"])' <<<"$STATE_JSON")"
  case "$STATE" in
    succeeded)
      break
      ;;
    failed|rolled_back|rollback_failed|canceled)
      python3 -c 'import json,sys; d=json.load(sys.stdin); print("Takeover activation failed:", d.get("failure_code"), d.get("failure_message"))' <<<"$STATE_JSON"
      exit 1
      ;;
  esac
  sleep 2
done

STATE_JSON="$(api_get "/api/control/v1/takeovers/$TAKEOVER_ID/")"
STATE="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["state"])' <<<"$STATE_JSON")"
[[ "$STATE" == "succeeded" ]] || { echo "Takeover did not succeed."; exit 1; }

curl -kfsS --max-time 15 "https://$DOMAIN/" >/dev/null
curl -kfsS --max-time 15 "https://$DOMAIN/api/v1/health/" >/dev/null
FINAL="$(api_get "/api/control/v1/projects/$PROJECT_ID/")"
python3 -c 'import json,sys; d=json.load(sys.stdin); s=next(x for x in d["services"] if x["name"]=="frontend"); print("Frontend:", s["lifecycle_state"], s["repository"], s["root_directory"], s["service_port"]); print("Domain:", d["domains"][0]["hostname"], d["domains"][0]["status"], d["domains"][0].get("management_mode"))' <<<"$FINAL"

echo "Cafino frontend controlled takeover completed successfully."
