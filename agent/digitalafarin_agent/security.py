import secrets

from fastapi import Header, HTTPException, status

from .config import get_settings


def require_agent_token(authorization: str | None = Header(default=None)) -> None:
    expected = get_settings().platform_agent_token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
