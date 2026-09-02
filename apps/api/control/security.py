from dataclasses import dataclass
import hashlib
import secrets

_ALLOWED_KINDS = {"enroll", "agent", "service"}


@dataclass(frozen=True)
class IssuedSecret:
    cleartext: str
    prefix: str
    digest: str


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def issue_secret(kind: str) -> IssuedSecret:
    if kind not in _ALLOWED_KINDS:
        raise ValueError("unsupported secret kind")
    prefix = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    return IssuedSecret(
        cleartext=f"da_{kind}_{prefix}.{secret}",
        prefix=prefix,
        digest=_digest(secret),
    )


def parse_secret(value: str, expected_kind: str) -> tuple[str, str]:
    if expected_kind not in _ALLOWED_KINDS:
        raise ValueError("unsupported secret kind")
    marker = f"da_{expected_kind}_"
    if not value.startswith(marker) or "." not in value:
        raise ValueError("invalid secret format")
    prefix, secret = value[len(marker):].split(".", 1)
    if not prefix or not secret:
        raise ValueError("invalid secret format")
    return prefix, secret


def verify_secret(secret: str, digest: str) -> bool:
    return secrets.compare_digest(_digest(secret), digest)
