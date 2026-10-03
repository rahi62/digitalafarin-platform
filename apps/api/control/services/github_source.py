import base64
import json
import os
import time
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
    raw_key = os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n").strip()
    if not app_id or not raw_key:
        raise GitHubSourceError("GitHub App is not configured")
    now = int(time.time())
    header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64url(json.dumps({"iat": now - 60, "exp": now + 540, "iss": app_id}, separators=(",", ":")).encode())
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


def download_archive(repository: str, exact_commit: str, *, max_bytes: int = 100 * 1024 * 1024) -> bytes:
    if len(exact_commit) != 40 or any(ch not in "0123456789abcdef" for ch in exact_commit):
        raise GitHubSourceError("exact commit is required")
    owner, name = repository_name(repository)
    headers = {
        "Authorization": f"Bearer {installation_token(repository)}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(f"https://api.github.com/repos/{owner}/{name}/tarball/{exact_commit}", headers=headers)
            response.raise_for_status()
            data = response.content
    except httpx.HTTPError as exc:
        raise GitHubSourceError("unable to download GitHub source") from exc
    if len(data) > max_bytes:
        raise GitHubSourceError("GitHub source archive exceeds size limit")
    return data
