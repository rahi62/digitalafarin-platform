import os
import re
import subprocess
from pathlib import Path

from .redaction import redact


HOSTNAME = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DomainError(RuntimeError):
    pass


def _run(argv: list[str]) -> None:
    try:
        result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=120, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DomainError(type(exc).__name__) from exc
    if result.returncode != 0:
        raise DomainError(redact(result.stderr or "domain command failed")[:500])


def configure_domain(
    payload: dict,
    *,
    sites_available: Path = Path("/etc/nginx/sites-available"),
    sites_enabled: Path = Path("/etc/nginx/sites-enabled"),
) -> dict:
    if set(payload) != {"hostname", "service_port"}:
        raise DomainError("invalid domain configuration payload")
    hostname = payload["hostname"]
    port = payload["service_port"]
    if not isinstance(hostname, str) or not HOSTNAME.fullmatch(hostname):
        raise DomainError("invalid hostname")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise DomainError("invalid service port")
    sites_available.mkdir(parents=True, exist_ok=True)
    sites_enabled.mkdir(parents=True, exist_ok=True)
    final = sites_available / f"digitalafarin-{hostname}.conf"
    staging = sites_available / f".digitalafarin-{hostname}.staging"
    enabled = sites_enabled / f"digitalafarin-{hostname}.conf"
    staging.write_text(
        "server {\n"
        "    listen 80;\n"
        f"    server_name {hostname};\n"
        "    location / {\n"
        f"        proxy_pass http://127.0.0.1:{port};\n"
        "        proxy_set_header Host $host;\n"
        "        proxy_set_header X-Forwarded-Proto $scheme;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    if enabled.exists() or enabled.is_symlink():
        enabled.unlink()
    enabled.symlink_to(staging)
    try:
        _run(["nginx", "-t"])
    except Exception:
        enabled.unlink(missing_ok=True)
        staging.unlink(missing_ok=True)
        raise
    os.replace(staging, final)
    enabled.unlink(missing_ok=True)
    enabled.symlink_to(final)
    _run(["systemctl", "reload", "nginx.service"])
    return {"config_path": str(final), "configured": True}


def enable_ssl(payload: dict) -> dict:
    if set(payload) != {"hostname", "email"}:
        raise DomainError("invalid SSL payload")
    hostname = payload["hostname"]
    email = payload["email"]
    if not HOSTNAME.fullmatch(hostname) or not EMAIL.fullmatch(email):
        raise DomainError("invalid SSL identity")
    _run([
        "certbot", "--nginx", "--non-interactive", "--agree-tos", "--redirect",
        "--email", email, "-d", hostname,
    ])
    return {"ssl_enabled": True}
