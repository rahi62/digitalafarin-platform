#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="${1:-https://github.com/rahi62/coffino.git}"
API_ENV="/etc/digitalafarin-platform/api.env"
API_DIR="/opt/digitalafarin-platform/apps/api"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root."
  exit 1
fi
[[ -r "$API_ENV" ]] || { echo "API env not found: $API_ENV"; exit 1; }
[[ -x "$API_DIR/.venv/bin/python" ]] || { echo "API venv not found."; exit 1; }

set -a
source "$API_ENV"
set +a

cd "$API_DIR"
"$API_DIR/.venv/bin/python" - "$REPOSITORY" <<'PY'
import os
import sys
import httpx
from control.services.github_source import app_headers, repository_name, GitHubSourceError

repository = sys.argv[1]
owner, name = repository_name(repository)
key_file = os.getenv("GITHUB_APP_PRIVATE_KEY_FILE", "").strip()
configured = {
    "GITHUB_APP_ID": bool(os.getenv("GITHUB_APP_ID", "").strip()),
    "GITHUB_APP_PRIVATE_KEY": bool(
        os.getenv("GITHUB_APP_PRIVATE_KEY", "").strip()
        or (key_file and __import__("pathlib").Path(key_file).is_file())
    ),
    "GITHUB_APP_SLUG": bool(os.getenv("GITHUB_APP_SLUG", "").strip()),
}
print("GitHub App config:", ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in configured.items()))
if not configured["GITHUB_APP_ID"] or not configured["GITHUB_APP_PRIVATE_KEY"]:
    print("RESULT=app_not_configured")
    raise SystemExit(2)

try:
    headers = app_headers()
except GitHubSourceError as exc:
    print(f"RESULT=app_credentials_invalid ({exc})")
    raise SystemExit(3)

with httpx.Client(timeout=15.0) as client:
    installation = client.get(
        f"https://api.github.com/repos/{owner}/{name}/installation",
        headers=headers,
    )
    print("Repository installation lookup HTTP:", installation.status_code)
    if installation.status_code != 200:
        if installation.status_code == 404:
            print("RESULT=repository_not_in_app_installation")
        elif installation.status_code in {401, 403}:
            print("RESULT=app_auth_or_permission_denied")
        else:
            print("RESULT=installation_lookup_failed")
        raise SystemExit(4)

    data = installation.json()
    installation_id = data.get("id")
    selection = data.get("repository_selection")
    account = (data.get("account") or {}).get("login")
    print("Installation:", installation_id, "account=", account, "selection=", selection)

    token_response = client.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers=headers,
        json={"repositories": [name], "permissions": {"contents": "read"}},
    )
    print("Installation token HTTP:", token_response.status_code)
    if token_response.status_code not in {200, 201}:
        print("RESULT=installation_token_failed")
        raise SystemExit(5)

    token = token_response.json().get("token", "")
    if not token:
        print("RESULT=installation_token_missing")
        raise SystemExit(6)

    repo_response = client.get(
        f"https://api.github.com/repos/{owner}/{name}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    print("Repository access HTTP:", repo_response.status_code)
    if repo_response.status_code != 200:
        print("RESULT=repository_access_failed")
        raise SystemExit(7)

print("RESULT=ok")
PY
