#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
python=${1:-/opt/digitalafarin-platform/agent/.venv/bin/python}
probe="$project_root/agent/tests/integration/sealed_release_probe.py"
test "$(ps -p 1 -o comm=)" = systemd
test "$(id -u)" -eq 0
allocation_root=$(mktemp -d /srv/digitalafarin/apps/.sealed-release-integration-XXXXXXXX)
chmod 0755 "$allocation_root"
unit="digitalafarin-sealed-integration-$(basename "$allocation_root").service"
cleanup() {
    systemctl stop "$unit" >/dev/null 2>&1 || true
    systemctl reset-failed "$unit" >/dev/null 2>&1 || true
    rm -rf "$allocation_root"
}
trap cleanup EXIT INT TERM
PYTHONPATH="$project_root/agent" /usr/bin/systemd-run \
    --quiet --wait --collect --pipe --unit="$unit" \
    --property=Type=oneshot --property=User=root --property=Group=digitalafarin-agent \
    --property=NoNewPrivileges=yes --property=PrivateTmp=yes \
    --property=ProtectHome=yes --property=ProtectSystem=strict \
    --property=ProtectKernelTunables=yes --property=ProtectKernelModules=yes \
    --property=ProtectControlGroups=yes --property=LockPersonality=yes \
    --property="ReadWritePaths=$allocation_root" \
    --setenv="PYTHONPATH=$project_root/agent" -- \
    "$python" "$probe" --allocation-root "$allocation_root"
