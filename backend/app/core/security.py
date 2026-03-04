from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt import InvalidTokenError

from app.core.config import settings


def create_access_token(user_id: str, expires_minutes: int | None = None) -> str:
    # Validate format early so downstream ownership checks are consistent.
    UUID(user_id)
    ttl = expires_minutes or settings.jwt_access_token_expire_minutes
    expire_at = datetime.now(UTC) + timedelta(minutes=ttl)
    payload = {
        "sub": user_id,
        "exp": expire_at,
        "iat": datetime.now(UTC),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except InvalidTokenError as exc:
        raise ValueError("Invalid token") from exc

    if payload.get("type") != "access":
        raise ValueError("Invalid token type")
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise ValueError("Invalid token subject")
    UUID(sub)
    return payload

