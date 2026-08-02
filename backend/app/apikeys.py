"""Developer API keys: issue, authenticate, revoke.

These are distinct from the provider keys in `app/llm/gateway.py`. A
provider key is a secret StateJar holds *on the user's behalf* to call
OpenRouter, so it is encrypted and decryptable. A developer API key is a
credential the user presents *to StateJar*, so it is stored as a one-way
SHA-256 hash and can never be recovered — only shown once at creation.

SHA-256 with no work factor is the right choice here, unlike for passwords:
the key is 256 bits of `secrets` entropy rather than something memorable, so
there is nothing to brute-force, and a slow KDF would tax every API request
for no gain.

Scope: an API key authenticates the data plane (memory, chat, audit, usage).
It deliberately cannot reach account management — issuing more keys or
reading provider keys stays JWT-only, so a leaked key cannot escalate into
a permanent foothold or exfiltrate the user's OpenRouter credit.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    select,
)
from sqlalchemy.orm import Session

from app.auth.models import users
from app.auth.routes import UserOut, get_current_user, user_from_bearer
from app.database import get_db
from app.timeutil import iso_utc

apikeys_metadata = MetaData()

api_keys = Table(
    "api_keys",
    apikeys_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False, index=True),
    # hex sha256 of the presented key; the key itself is never stored
    Column("key_hash", String(64), nullable=False, unique=True),
    Column("key_last4", String(8), nullable=False),
    Column("label", String(100), nullable=True),
    Column("created_at", DateTime, nullable=False),
    # NULL means "never expires" — every key issued before migration 005
    Column("expires_at", DateTime, nullable=True),
    Column("last_used_at", DateTime, nullable=True),
    # soft revoke: the row survives so an audit trail can still name the key
    Column("revoked_at", DateTime, nullable=True),
)

# Offered expiries. "never" is available but not the default: a key that
# cannot expire is a credential nobody ever has to think about again.
EXPIRY_CHOICES: dict[str, timedelta | None] = {
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "365d": timedelta(days=365),
    "never": None,
}
DEFAULT_EXPIRY = "30d"
EXPIRING_SOON = timedelta(days=7)


def key_status(row: Any, now: datetime | None = None) -> str:
    """active | expiring_soon | expired | revoked."""
    now = now or datetime.now(timezone.utc)
    if row["revoked_at"] is not None:
        return "revoked"
    expires_at = row["expires_at"]
    if expires_at is None:
        return "active"
    if expires_at.tzinfo is None:          # naive column, stored as UTC
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        return "expired"
    return "expiring_soon" if expires_at - now <= EXPIRING_SOON else "active"

KEY_PREFIX = "sj_live_"
_KEY_ENTROPY_BYTES = 32

router = APIRouter(prefix="/apikeys", tags=["developer api"])

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


def generate_key() -> str:
    """A fresh key. Returned to the caller once and never stored in the clear."""
    return f"{KEY_PREFIX}{secrets.token_urlsafe(_KEY_ENTROPY_BYTES)}"


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class ApiKeyExpired(Exception):
    """A key that was valid and is not any more — distinct from an unknown one."""

    def __init__(self, expires_at: datetime) -> None:
        self.expires_at = expires_at
        super().__init__(f"API key expired on {expires_at.date().isoformat()}")


def user_for_api_key(db: Session, presented: str) -> UserOut | None:
    """Resolve a presented key to its owner.

    Returns None for an unknown or revoked key, and raises ApiKeyExpired for
    one that has simply run out — the caller turns that into a message the
    developer can act on rather than a generic 401.
    """
    row = db.execute(
        select(api_keys.c.id, api_keys.c.user_id, api_keys.c.expires_at,
               api_keys.c.revoked_at)
        .where(api_keys.c.key_hash == hash_key(presented))
        .where(api_keys.c.revoked_at.is_(None))
    ).mappings().first()
    if row is None:
        return None

    now = datetime.now(timezone.utc)
    expires_at = row["expires_at"]
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise ApiKeyExpired(expires_at)

    user = db.execute(
        select(users).where(users.c.id == row["user_id"])
    ).mappings().first()
    if user is None:
        return None

    # "last used" is only meaningful if it is written on use; a failure to
    # record it must never cost the caller their request
    try:
        db.execute(
            api_keys.update().where(api_keys.c.id == row["id"]).values(last_used_at=now)
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    return UserOut(id=user["id"], email=user["email"])


def get_api_caller(
    api_key: str | None = Security(_api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: Session = Depends(get_db),
) -> UserOut:
    """Authenticate the data plane by either X-API-Key or a console JWT.

    X-API-Key wins when both are present, so a browser session cannot mask a
    misconfigured integration. The JWT path is byte-for-byte the console's.
    """
    if api_key:
        try:
            caller = user_for_api_key(db, api_key)
        except ApiKeyExpired as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))
        if caller is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "invalid or revoked API key"
            )
        return caller
    return user_from_bearer(credentials, db)


# --- management (JWT only) ----------------------------------------------------


class GenerateApiKeyIn(BaseModel):
    expires_in: str = Field(default=DEFAULT_EXPIRY, max_length=10)
    label: str | None = Field(default=None, max_length=100)


class NewApiKeyOut(BaseModel):
    id: int
    api_key: str  # the only time this is ever returned
    key_last4: str
    label: str | None = None
    created_at: str
    expires_at: str | None = None


class ApiKeyOut(BaseModel):
    id: int
    key_last4: str
    label: str | None = None
    created_at: str
    expires_at: str | None = None
    last_used_at: str | None = None
    revoked: bool = False
    status: str = "active"


@router.post("/generate", response_model=NewApiKeyOut, status_code=status.HTTP_201_CREATED)
def generate_api_key(
    body: GenerateApiKeyIn | None = None,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NewApiKeyOut:
    """Issue a key. The plaintext in this response is unrecoverable afterwards."""
    body = body or GenerateApiKeyIn()
    if body.expires_in not in EXPIRY_CHOICES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"expires_in must be one of {', '.join(EXPIRY_CHOICES)}",
        )
    key = generate_key()
    created_at = datetime.now(timezone.utc)
    lifetime = EXPIRY_CHOICES[body.expires_in]
    expires_at = created_at + lifetime if lifetime else None
    label = (body.label or "").strip() or None

    result = db.execute(
        api_keys.insert().values(
            user_id=user.id,
            key_hash=hash_key(key),
            key_last4=key[-4:],
            label=label,
            created_at=created_at,
            expires_at=expires_at,
        )
    )
    db.commit()
    return NewApiKeyOut(
        id=result.inserted_primary_key[0],
        api_key=key,
        key_last4=key[-4:],
        label=label,
        created_at=iso_utc(created_at),
        expires_at=iso_utc(expires_at),
    )


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApiKeyOut]:
    """Every key the user has, newest first — last 4 characters only.

    Expired and revoked keys are included: hiding them would leave a
    developer wondering why a key they still have in an .env stopped working.
    """
    rows = db.execute(
        select(api_keys)
        .where(api_keys.c.user_id == user.id)
        .order_by(api_keys.c.id.desc())
    ).mappings()
    return [
        ApiKeyOut(
            id=r["id"],
            key_last4=r["key_last4"],
            label=r["label"],
            created_at=iso_utc(r["created_at"]),
            expires_at=iso_utc(r["expires_at"]),
            last_used_at=iso_utc(r["last_used_at"]),
            revoked=r["revoked_at"] is not None,
            status=key_status(r),
        )
        for r in rows
    ]


@router.delete("/{key_id}")
def revoke_api_key(
    key_id: int,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Revoke immediately. Scoped to the owner, so ids cannot be probed."""
    result = db.execute(
        api_keys.update()
        .where(api_keys.c.id == key_id)
        .where(api_keys.c.user_id == user.id)
        .where(api_keys.c.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()
    if not result.rowcount:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown or already revoked key")
    return {"id": key_id, "revoked": True}
