import os

from cryptography.fernet import Fernet, InvalidToken


_KEY_ENV = "TELEGRAM_CREDENTIAL_ENCRYPTION_KEY"


def _fernet() -> Fernet:
    raw = os.getenv(_KEY_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"{_KEY_ENV} is not configured")
    try:
        return Fernet(raw.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"{_KEY_ENV} is invalid") from exc


def encrypt_bot_token(token: str) -> str:
    value = token.strip()
    if not value:
        raise ValueError("bot token cannot be empty")
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_bot_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("stored Telegram credential cannot be decrypted") from exc
