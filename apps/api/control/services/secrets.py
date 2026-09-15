import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class SecretConfigurationError(RuntimeError):
    pass


def _fernet() -> MultiFernet:
    raw_keys = [value.strip() for value in os.getenv("PLATFORM_SECRET_KEYS", "").split(",") if value.strip()]
    if not raw_keys:
        raise SecretConfigurationError("PLATFORM_SECRET_KEYS is not configured")
    try:
        return MultiFernet([Fernet(value.encode()) for value in raw_keys])
    except (TypeError, ValueError) as exc:
        raise SecretConfigurationError("PLATFORM_SECRET_KEYS is invalid") from exc


def encrypt_secret(value: str) -> str:
    if not value:
        raise ValueError("secret value cannot be empty")
    return "v1:" + _fernet().encrypt(value.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext.startswith("v1:"):
        raise SecretConfigurationError("unsupported secret version")
    try:
        return _fernet().decrypt(ciphertext[3:].encode()).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise SecretConfigurationError("secret decryption failed") from exc
