import secrets

from fastapi import Header, HTTPException, status

from digitalafarin_agent.config import get_settings


def require_agent_token(authorization: str | None = Header(default=None)) -> None:
    expected = get_settings().platform_agent_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Legacy agent API disabled",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    supplied = authorization[7:].strip()
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
