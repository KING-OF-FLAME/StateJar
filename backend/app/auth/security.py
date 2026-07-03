"""Password hashing (bcrypt) and JWT helpers for StateJar auth."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import get_settings

_ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=24)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": "user",
        "iat": now,
        "exp": now + TOKEN_TTL,
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT; raises jwt.PyJWTError on any failure."""
    return jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGORITHM])
