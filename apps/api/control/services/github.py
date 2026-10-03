import base64
import json
import os
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class GitHubSourceAuthError(RuntimeError):
    pass


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _app_jwt(app_id: str, private_key_pem: str) -> str:
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(
        json.dumps({"iat": now - 60, "exp": now + 540, "iss": app_id}, separators=(",", ":")).encode()
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    try:
        key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    except (TypeError, ValueError) as exc:
        raise GitHubSourceAuthError("GitHub App private key is invalid.") from exc
    return f"{header}.{payload}.{_b64url(signature)}"


def installation_token_for_repository(repository: str) -> str:
    app_id = os.getenv("GITHUB_APP_ID", "").strip()
    installation_id = os.getenv("GITHUB_APP_INSTALLATION_ID", "").strip()
    private_key = os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n").strip()
    if not app_id or not installation_id or not private_key:
        raise GitHubSourceAuthError("GitHub App source authentication is not configured.")

    repo = repository.removesuffix(".git")
    prefix = "https://github.com/"
    if not repo.startswith(prefix):
        raise GitHubSourceAuthError("Repository is not a supported GitHub HTTPS repository.")
    full_name = repo[len(prefix):]
    if full_name.count("/") != 1:
        raise GitHubSourceAuthError("Repository is not a supported GitHub repository.")

    jwt = _app_jwt(app_id, private_key)
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            repo_response = client.get(
                f"https://api.github.com/repos/{full_name}/installation",
                headers=headers,
            )
            repo_response.raise_for_status()
            if str(repo_response.json().get("id")) != installation_id:
                raise GitHubSourceAuthError("Repository is not authorized by the configured GitHub installation.")
            token_response = client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers=headers,
                json={"repositories": [full_name.split("/", 1)[1]], "permissions": {"contents": "read"}},
            )
            token_response.raise_for_status()
            token = token_response.json().get("token", "")
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise GitHubSourceAuthError("Unable to obtain GitHub installation token.") from exc
    if not isinstance(token, str) or not token:
        raise GitHubSourceAuthError("GitHub installation token response is invalid.")
    return token
