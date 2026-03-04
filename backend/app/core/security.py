from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt import InvalidTokenError

from app.core.config import settings

PBKDF2_ITERATIONS = 600_000
PBKDF2_SALT_BYTES = 16


def hash_password(password: str) -> str:
    password_text = password.strip()
    if len(password_text) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(password_text) > 128:
        raise ValueError("Password must be 128 characters or fewer")

    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password_text.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_b64}${digest_b64}"


def verify_password(password: str, encoded_hash: str) -> bool:
    if not encoded_hash:
        return False
    try:
        algo, iter_text, salt_b64, digest_b64 = encoded_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_text)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected_digest = base64.b64decode(digest_b64.encode("ascii"))
    except Exception:
        return False

    candidate_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate_digest, expected_digest)


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

