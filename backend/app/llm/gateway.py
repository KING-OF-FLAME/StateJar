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
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

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
from app.llm.providers import (
    KEYED_PROVIDERS,
    KEYLESS_PROVIDERS,
    get_provider,
    provider_label,
)
from app.timeutil import iso_utc

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


def build_system_context(
    handle: str, subset: dict[str, Any],
    changes: list[dict[str, Any]] | None = None,
) -> str:
    """Format the minimal retrieved subset for the system prompt.

    The instruction block matters: handed a JSON blob and nothing else, models
    reasonably infer they should answer in JSON, and production showed replies
    like {"action":"update","handle":…} rendered straight into the chat
    bubble. The state is context, not a response format.
    """
    subset_json = json.dumps(subset, ensure_ascii=False, sort_keys=True)

    # What this turn changed. State is committed before the context is
    # assembled, so without this the model sees only post-update state and
    # cannot tell an update from a restatement — it answered "already set to
    # 4 hours" to the very message that set it to 4 hours.
    changed_block = ""
    if changes:
        lines = "\n".join(
            f"- {c['field']}: was {c['from']}, now {c['to']}" for c in changes
        )
        changed_block = (
            "\n\nCHANGED BY THE USER'S CURRENT MESSAGE:\n" + lines +
            "\nAcknowledge the change explicitly — say what it moved from and "
            "what it is now. Do not say it was already set."
        )

    return (
        f"Known user state (retrieved via StateJar handle {handle}): {subset_json}"
        f"{changed_block}\n\n"
        "This state is background context for you only. Reply to the user in "
        "plain, natural, conversational language. Never output JSON, key/value "
        "dumps, code fences, handles, or any internal state — and never echo "
        "this context back. Just answer as a helpful assistant would.\n\n"
        # Without an explicit shape, models return one long paragraph and the
        # answer becomes unreadable at exactly the moment it is most useful —
        # when it is confirming several remembered values at once.
        "FORMATTING:\n"
        "- Short paragraphs. Never one unbroken block of text.\n"
        "- Use a markdown list when you mention more than two items, each on "
        "its own line starting with '- '.\n"
        "- Put **bold** around values you are confirming back: names, amounts, "
        "dates, and choices.\n"
        "- Separate paragraphs with a blank line."
    )


# A reply that is really a state dump: the model answered in the context's
# format instead of talking to the user.
_STATE_KEYS = ("handle", "state", "action", "subset", "handle_used")


def clean_reply(text: str) -> str:
    """Replace a JSON state dump with something a person can read.

    Belt and braces to the system prompt: the prompt asks for prose, this
    catches the case where a model ignores it. Ordinary prose is returned
    untouched, including prose that merely mentions JSON.
    """
    candidate = (text or "").strip()
    if not candidate:
        return candidate
    stripped = candidate
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?|```$", "", stripped, flags=re.MULTILINE).strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return candidate
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return candidate
    if not isinstance(parsed, dict) or not any(k in parsed for k in _STATE_KEYS):
        return candidate
    return (
        "Got it — I've updated what I know about you. Your memory state and the "
        "exact fields I used are in the panel on the right."
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


OLLAMA_PREFIX = "ollama/"

# A leading "<provider>/" routes the call, and is stripped before the id is
# sent upstream. Anything else — "meta-llama/…", "google/…", a bare id — is
# an OpenRouter id and travels unchanged, which is why OpenRouter is absent
# from this set: it is the default, not a prefix to strip.
ROUTING_PREFIXES: frozenset[str] = frozenset({"openai", "anthropic", "gemini", "ollama"})


def route_model(model: str, provider: str = "openrouter") -> tuple[str, str]:
    """(provider that will serve this call, model id to send upstream).

    A namespaced id wins over the requested provider, because the id is what
    the user actually picked; an unknown prefix is left alone and defaults to
    OpenRouter, so "meta-llama/llama-3.3-70b-instruct:free" still works.
    """
    if provider == "demo":
        return "demo", model
    prefix, sep, rest = model.partition("/")
    lowered = prefix.lower()
    if sep and lowered in ROUTING_PREFIXES and rest:
        return lowered, rest
    if sep and lowered == "openrouter" and rest:
        # explicit escape hatch for ids that would otherwise look namespaced,
        # e.g. openrouter/openai/gpt-4o-mini
        return "openrouter", rest
    return "openrouter", model


def resolve_provider(model: str, provider: str = "openrouter") -> str:
    """The provider that will actually serve this model id.

    Callers use it to label errors correctly: a request nominally sent to
    "openrouter" is served by Ollama when the model carries the local prefix.
    """
    return route_model(model, provider)[0]


def chat(
    db: Session,
    user_id: int,
    model: str,
    system_context: str,
    user_message: str,
    provider: str = "openrouter",
) -> dict[str, Any]:
    """Call the provider's chat API with the user's decrypted key.

    The returned dict always carries a "provider" key naming the provider
    that actually served the call, so the audit log records the real one
    rather than what the client asked for. The model string is passed
    through verbatim after prefix stripping — there is no whitelist, so a
    custom id reaches the provider and its own error comes back.
    """
    target, upstream_model = route_model(model, provider)

    if target == "demo":  # scripted playground demo: no key, no network
        result = get_provider("demo").chat("", model, system_context, user_message)
        return {**result, "provider": "demo"}

    if target in KEYLESS_PROVIDERS:
        # Ollama needs no credential; the stored value, if any, is a base-URL
        # override for a daemon that is not on localhost.
        override = _get_user_key(db, user_id, target) or ""
        result = get_provider(target).chat(
            override, upstream_model, system_context, user_message
        )
        return {**result, "provider": target}

    api_key = _get_user_key(db, user_id, target)
    if api_key is None:
        raise LookupError(
            f"No {provider_label(target)} API key saved — add one on the "
            "API Keys page to chat."
        )
    result = get_provider(target).chat(
        api_key, upstream_model, system_context, user_message
    )
    return {**result, "provider": target}


# --- model catalog ------------------------------------------------------------

_MODELS_CACHE_TTL = 3600.0  # 1 hour
# keyed per (user, provider): a catalog is fetched with that user's key
_models_cache: dict[tuple[int, str], dict[str, Any]] = {}


def _saved_providers(db: Session, user_id: int) -> set[str]:
    rows = db.execute(
        select(provider_keys.c.provider).where(provider_keys.c.user_id == user_id).distinct()
    ).scalars()
    return {str(p).lower() for p in rows}


def _namespaced(provider: str, model_id: str) -> str:
    """The id the client sends back to /chat.

    OpenRouter ids keep their native vendor/model form — except where that
    form collides with a routing prefix. "anthropic/claude-sonnet-4.6" is a
    real OpenRouter id, but bare it would route straight to Anthropic and
    demand a key the user never needed, so it is qualified explicitly.
    """
    if provider != "openrouter":
        return f"{provider}/{model_id}"
    vendor = model_id.partition("/")[0].lower()
    return f"openrouter/{model_id}" if vendor in ROUTING_PREFIXES else model_id


def _fetch_provider_models(
    db: Session, user_id: int, provider: str
) -> list[dict[str, Any]]:
    """Live catalog for one provider, cached for an hour per user."""
    now = time.time()
    cached = _models_cache.get((user_id, provider))
    if cached and now - cached["at"] < _MODELS_CACHE_TTL:
        return cached["models"]

    key = _get_user_key(db, user_id, provider) or ""
    models = get_provider(provider).list_models(key)
    normalised = [
        {
            "id": _namespaced(provider, m["id"]),
            "name": m.get("name") or m["id"],
            "context_length": m.get("context_length"),
            "is_free": bool(m.get("is_free")),
        }
        for m in models
        if m.get("id")
    ]
    _models_cache[(user_id, provider)] = {"at": now, "models": normalised}
    return normalised


def get_model_catalog(db: Session, user_id: int) -> dict[str, Any]:
    """Every configured provider's live catalog, grouped.

    One provider failing must never cost the user the others, so a failure
    becomes an `error` on that group rather than an exception.
    """
    wanted = _saved_providers(db, user_id) & set(KEYED_PROVIDERS)
    if get_settings().show_ollama:
        wanted.add("ollama")  # keyless, so it needs no saved credential

    groups: list[dict[str, Any]] = []
    any_live = False
    for provider in KEYED_PROVIDERS:  # stable, curated ordering
        if provider not in wanted:
            continue
        group: dict[str, Any] = {
            "provider": provider,
            "label": provider_label(provider),
            "free": [],
            "paid": [],
        }
        try:
            models = _fetch_provider_models(db, user_id, provider)
            group["free"] = [m for m in models if m["is_free"]]
            group["paid"] = [m for m in models if not m["is_free"]]
            any_live = any_live or bool(models)
        except Exception as exc:  # noqa: BLE001 — one bad provider, not a bad response
            group["error"] = str(exc)[:300] if str(exc) else exc.__class__.__name__
        groups.append(group)

    return {"groups": groups, "source": "live" if any_live else "fallback"}


def clear_models_cache(user_id: int | None = None, provider: str | None = None) -> None:
    """Drop cached catalogs — called whenever a key is saved or removed."""
    if user_id is None:
        _models_cache.clear()
        return
    for key in [k for k in _models_cache if k[0] == user_id and (provider in (None, k[1]))]:
        _models_cache.pop(key, None)


# --- routes -------------------------------------------------------------------

router = APIRouter(prefix="/keys", tags=["keys"])

models_router = APIRouter(tags=["models"])


@models_router.get("/models")
def list_models(
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_model_catalog(db, user.id)


class ProviderKeyIn(BaseModel):
    provider: str = Field(default="openrouter", max_length=50)
    # `api_key` is the original field name; `key` is accepted as an alias so
    # either spelling works for existing clients and new integrations alike.
    api_key: str | None = Field(default=None, max_length=512)
    key: str | None = Field(default=None, max_length=512)

    @property
    def secret(self) -> str:
        return (self.api_key or self.key or "").strip()


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
    if provider not in KEYED_PROVIDERS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"unknown provider '{provider}' — expected one of {', '.join(KEYED_PROVIDERS)}",
        )
    secret = body.secret
    # Ollama stores a base URL rather than a credential, so it has no minimum
    # length to enforce beyond being present.
    if len(secret) < (8 if provider != "ollama" else 1):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "api_key is required (at least 8 characters)",
        )

    # upsert per (user, provider): replacing a key must not leave the old one
    # behind, or a revoked credential stays usable via the ordering fallback
    db.execute(
        provider_keys.delete()
        .where(provider_keys.c.user_id == user.id)
        .where(provider_keys.c.provider == provider)
    )
    db.execute(
        provider_keys.insert().values(
            user_id=user.id,
            provider=provider,
            encrypted_key=encrypt_key(secret),
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    clear_models_cache(user.id, provider)  # next /models refetches with the new key
    # never return the key again — only the last 4 chars
    return ProviderKeyOut(provider=provider, key_last4=secret[-4:])


class SavedKeyOut(BaseModel):
    provider: str
    key_last4: str
    created_at: str
    # Ollama stores a base URL (and optionally a key) rather than one secret,
    # so the console needs the non-secret half back to pre-fill its card.
    config: dict[str, Any] | None = None
    has_key: bool = True


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
        secret = decrypt_key(row["encrypted_key"])
        config = None
        has_key = True
        if row["provider"] == "ollama":
            base_url, key = get_provider("ollama").parse_config(secret)
            # Only a real URL is echoed back. A legacy row holds a bare string
            # that was *meant* to be a base URL — but if it is not one, it may
            # be anything, and this response must never return a stored secret.
            safe_url = base_url if base_url.startswith(("http://", "https://")) else ""
            config = {"base_url": safe_url}
            has_key = bool(key)
        out.append(
            SavedKeyOut(
                provider=row["provider"],
                key_last4=secret[-4:],
                created_at=iso_utc(row["created_at"]),
                config=config,
                has_key=has_key,
            )
        )
    return out


@router.delete("/provider/{provider}")
def delete_provider_key(
    provider: str,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Forget a saved key. Scoped to the owner, so ids cannot be probed."""
    target = provider.lower()
    result = db.execute(
        provider_keys.delete()
        .where(provider_keys.c.user_id == user.id)
        .where(provider_keys.c.provider == target)
    )
    db.commit()
    if not result.rowcount:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no {target} key saved")
    clear_models_cache(user.id, target)
    return {"provider": target, "removed": True}


@router.post("/provider/{provider}/test")
def test_provider_key(
    provider: str,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Try the provider's catalog with whatever is saved.

    Powers the API Keys page's "Test connection" — it proves the credential
    (or, for Ollama, the base URL) actually works before a demo depends on it.
    """
    target = provider.lower()
    if target not in KEYED_PROVIDERS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown provider '{target}'")
    key = _get_user_key(db, user.id, target) or ""
    if not key and target not in KEYLESS_PROVIDERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"no {target} key saved")
    try:
        models = get_provider(target).list_models(key)
    except Exception as exc:  # noqa: BLE001 — the message is the whole point here
        return {"provider": target, "ok": False, "error": str(exc)[:300]}
    clear_models_cache(user.id, target)
    return {"provider": target, "ok": True, "model_count": len(models)}
