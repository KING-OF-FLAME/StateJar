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
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
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
    Column("created_at", DateTime, nullable=False),
    # soft revoke: the row survives so an audit trail can still name the key
    Column("revoked_at", DateTime, nullable=True),
)

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


def user_for_api_key(db: Session, presented: str) -> UserOut | None:
    """Resolve a presented key to its owner, or None if unknown or revoked."""
    user_id = db.execute(
        select(api_keys.c.user_id)
        .where(api_keys.c.key_hash == hash_key(presented))
        .where(api_keys.c.revoked_at.is_(None))
    ).scalar_one_or_none()
    if user_id is None:
        return None
    row = db.execute(select(users).where(users.c.id == user_id)).mappings().first()
    return UserOut(id=row["id"], email=row["email"]) if row is not None else None


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
        caller = user_for_api_key(db, api_key)
        if caller is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "invalid or revoked API key"
            )
        return caller
    return user_from_bearer(credentials, db)


# --- management (JWT only) ----------------------------------------------------


class NewApiKeyOut(BaseModel):
    id: int
    api_key: str  # the only time this is ever returned
    key_last4: str
    created_at: str


class ApiKeyOut(BaseModel):
    id: int
    key_last4: str
    created_at: str


@router.post("/generate", response_model=NewApiKeyOut, status_code=status.HTTP_201_CREATED)
def generate_api_key(
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NewApiKeyOut:
    """Issue a key. The plaintext in this response is unrecoverable afterwards."""
    key = generate_key()
    created_at = datetime.now(timezone.utc)
    result = db.execute(
        api_keys.insert().values(
            user_id=user.id,
            key_hash=hash_key(key),
            key_last4=key[-4:],
            created_at=created_at,
        )
    )
    db.commit()
    return NewApiKeyOut(
        id=result.inserted_primary_key[0],
        api_key=key,
        key_last4=key[-4:],
        created_at=iso_utc(created_at),
    )


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApiKeyOut]:
    """Active keys, newest first — last 4 characters only."""
    rows = db.execute(
        select(api_keys.c.id, api_keys.c.key_last4, api_keys.c.created_at)
        .where(api_keys.c.user_id == user.id)
        .where(api_keys.c.revoked_at.is_(None))
        .order_by(api_keys.c.id.desc())
    ).mappings()
    return [
        ApiKeyOut(
            id=r["id"], key_last4=r["key_last4"], created_at=iso_utc(r["created_at"])
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
