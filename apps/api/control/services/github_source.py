import base64
import json
import os
import time
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class GitHubSourceError(RuntimeError):
    pass


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _app_jwt() -> str:
    app_id = os.getenv("GITHUB_APP_ID", "").strip()
    client_id = os.getenv("GITHUB_APP_CLIENT_ID", "").strip()
    issuer = client_id or app_id
    raw_key = os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n").strip()
    key_file = os.getenv("GITHUB_APP_PRIVATE_KEY_FILE", "").strip()
    if not raw_key and key_file:
        try:
            raw_key = Path(key_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise GitHubSourceError("GitHub App key file is unavailable") from exc
    if not issuer or not raw_key:
        raise GitHubSourceError("GitHub App is not configured")
    now = int(time.time())
    header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64url(json.dumps({"iat": now - 60, "exp": now + 540, "iss": issuer}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    try:
        key = serialization.load_pem_private_key(raw_key.encode(), password=None)
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    except (TypeError, ValueError) as exc:
        raise GitHubSourceError("GitHub App key is invalid") from exc
    return f"{header}.{payload}.{_b64url(signature)}"


def repository_name(repository: str) -> tuple[str, str]:
    parsed = urlparse(repository.removesuffix(".git"))
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise GitHubSourceError("unsupported GitHub repository")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise GitHubSourceError("invalid GitHub repository")
    return parts[0], parts[1]


def installation_token(repository: str) -> str:
    owner, name = repository_name(repository)
    jwt = _app_jwt()
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            installation = client.get(f"https://api.github.com/repos/{owner}/{name}/installation", headers=headers)
            installation.raise_for_status()
            installation_id = installation.json()["id"]
            response = client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers=headers,
                json={"repositories": [name], "permissions": {"contents": "read"}},
            )
            response.raise_for_status()
            token = response.json()["token"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise GitHubSourceError("unable to authorize GitHub source") from exc
    if not isinstance(token, str) or not token:
        raise GitHubSourceError("invalid GitHub installation token")
    return token


def download_bundle(repository: str, exact_commit: str, *, max_bytes: int = 100 * 1024 * 1024) -> bytes:
    if len(exact_commit) != 40 or any(ch not in "0123456789abcdef" for ch in exact_commit):
        raise GitHubSourceError("exact commit is required")
    owner, name = repository_name(repository)
    token = installation_token(repository)
    with tempfile.TemporaryDirectory(prefix="digitalafarin-source-") as temporary:
        root = Path(temporary)
        bare = root / "repo.git"
        bundle = root / "source.bundle"
        authenticated = f"https://x-access-token:{token}@github.com/{owner}/{name}.git"
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        try:
            subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True, timeout=30, env=env)
            subprocess.run(
                ["git", "-C", str(bare), "fetch", "--no-tags", authenticated, exact_commit],
                check=True, capture_output=True, timeout=120, env=env,
            )
            resolved = subprocess.run(
                ["git", "-C", str(bare), "rev-parse", "FETCH_HEAD"],
                check=True, capture_output=True, text=True, timeout=30, env=env,
            ).stdout.strip()
            if resolved != exact_commit:
                raise GitHubSourceError("GitHub returned a different commit")
            source_ref = "refs/heads/digitalafarin-source"
            subprocess.run(
                ["git", "-C", str(bare), "update-ref", source_ref, exact_commit],
                check=True, capture_output=True, timeout=30, env=env,
            )
            subprocess.run(
                ["git", "-C", str(bare), "bundle", "create", str(bundle), source_ref],
                check=True, capture_output=True, timeout=120, env=env,
            )
            data = bundle.read_bytes()
        except (OSError, subprocess.SubprocessError) as exc:
            raise GitHubSourceError("unable to prepare GitHub source bundle") from exc
    if len(data) > max_bytes:
        raise GitHubSourceError("GitHub source bundle exceeds size limit")
    return data


def app_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_app_jwt()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def installation_details(installation_id: int) -> dict:
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"https://api.github.com/app/installations/{installation_id}",
                headers=app_headers(),
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GitHubSourceError("unable to verify GitHub installation") from exc
    account = data.get("account") or {}
    return {
        "installation_id": int(data["id"]),
        "account_login": str(account.get("login") or ""),
        "account_type": str(account.get("type") or ""),
        "repository_selection": str(data.get("repository_selection") or ""),
        "suspended": data.get("suspended_at") is not None,
    }


def installation_access_token(installation_id: int) -> str:
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers=app_headers(),
                json={"permissions": {"contents": "read"}},
            )
            response.raise_for_status()
            token = response.json()["token"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise GitHubSourceError("unable to authorize GitHub installation") from exc
    if not isinstance(token, str) or not token:
        raise GitHubSourceError("invalid GitHub installation token")
    return token


def installation_repositories(installation_id: int) -> list[dict]:
    token = installation_access_token(installation_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    repositories = []
    page = 1
    try:
        with httpx.Client(timeout=10.0) as client:
            while page <= 10:
                response = client.get(
                    "https://api.github.com/installation/repositories",
                    headers=headers,
                    params={"per_page": 100, "page": page},
                )
                response.raise_for_status()
                items = response.json().get("repositories", [])
                for item in items:
                    repositories.append({
                        "id": int(item["id"]),
                        "full_name": str(item["full_name"]),
                        "html_url": str(item["html_url"]),
                        "default_branch": str(item.get("default_branch") or "main"),
                        "private": bool(item.get("private")),
                    })
                if len(items) < 100:
                    break
                page += 1
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise GitHubSourceError("unable to list GitHub installation repositories") from exc
    return repositories
