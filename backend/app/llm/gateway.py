"""LLM gateway for StateJar.

- Stores per-user provider API keys encrypted with AES-256-GCM.
- chat() decrypts the user's key and calls the provider with a
  system context built from the minimal retrieved state subset.

Keys are never returned after saving; responses expose only the last
four characters.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.auth.routes import UserOut, get_current_user
from app.config import get_settings
from app.database import get_db
from app.llm.providers import get_provider

llm_metadata = MetaData()

provider_keys = Table(
    "provider_keys",
    llm_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("provider", String(50), nullable=False),
    Column("encrypted_key", LargeBinary, nullable=False),
    Column("created_at", DateTime, nullable=False),
)

_NONCE_LEN = 12  # AES-GCM standard nonce size


def _aes_key() -> bytes:
    """Derive a 32-byte AES-256 key from the configured AES_KEY string."""
    return hashlib.sha256(get_settings().aes_key.encode("utf-8")).digest()


def encrypt_key(plaintext: str) -> bytes:
    """AES-256-GCM encrypt; output = nonce || ciphertext+tag."""
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(_aes_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ct


def decrypt_key(blob: bytes) -> str:
    """Inverse of encrypt_key; raises on tampering (GCM auth tag)."""
    nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    return AESGCM(_aes_key()).decrypt(nonce, ct, None).decode("utf-8")


def build_system_context(handle: str, subset: dict[str, Any]) -> str:
    """Format the minimal retrieved subset for the system prompt."""
    subset_json = json.dumps(subset, ensure_ascii=False, sort_keys=True)
    return (
        f"Known user state (retrieved via StateJar handle {handle}): {subset_json}"
    )


def _get_user_key(db: Session, user_id: int, provider: str) -> str | None:
    row = db.execute(
        select(provider_keys.c.encrypted_key)
        .where(provider_keys.c.user_id == user_id)
        .where(provider_keys.c.provider == provider)
        .order_by(provider_keys.c.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return decrypt_key(row) if row is not None else None


def chat(
    db: Session,
    user_id: int,
    model: str,
    system_context: str,
    user_message: str,
    provider: str = "openrouter",
) -> dict[str, Any]:
    """Call the provider's chat API with the user's decrypted key."""
    api_key = _get_user_key(db, user_id, provider)
    if api_key is None:
        raise LookupError(f"no {provider} key saved for user {user_id}")
    return get_provider(provider).chat(api_key, model, system_context, user_message)


# --- routes -------------------------------------------------------------------

router = APIRouter(prefix="/keys", tags=["keys"])


class ProviderKeyIn(BaseModel):
    provider: str = Field(default="openrouter", max_length=50)
    api_key: str = Field(min_length=8, max_length=512)


class ProviderKeyOut(BaseModel):
    provider: str
    key_last4: str
    saved: bool = True


@router.post("/provider", response_model=ProviderKeyOut, status_code=status.HTTP_201_CREATED)
def save_provider_key(
    body: ProviderKeyIn,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProviderKeyOut:
    provider = body.provider.lower()
    try:
        get_provider(provider)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown provider '{provider}'")

    db.execute(
        provider_keys.insert().values(
            user_id=user.id,
            provider=provider,
            encrypted_key=encrypt_key(body.api_key),
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    # never return the key again — only the last 4 chars
    return ProviderKeyOut(provider=provider, key_last4=body.api_key[-4:])


class SavedKeyOut(BaseModel):
    provider: str
    key_last4: str
    created_at: str


@router.get("/provider", response_model=list[SavedKeyOut])
def list_provider_keys(
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavedKeyOut]:
    """Latest saved key per provider — last 4 chars only, never the full key."""
    rows = db.execute(
        select(
            provider_keys.c.provider,
            provider_keys.c.encrypted_key,
            provider_keys.c.created_at,
        )
        .where(provider_keys.c.user_id == user.id)
        .order_by(provider_keys.c.id.desc())
    ).mappings()

    out: list[SavedKeyOut] = []
    seen: set[str] = set()
    for row in rows:
        if row["provider"] in seen:
            continue
        seen.add(row["provider"])
        out.append(
            SavedKeyOut(
                provider=row["provider"],
                key_last4=decrypt_key(row["encrypted_key"])[-4:],
                created_at=row["created_at"].isoformat(),
            )
        )
    return out
