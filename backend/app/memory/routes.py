"""StateJar pipeline routes: ingest → version → retrieve → chat → audit."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.apikeys import get_api_caller
from app.auth.routes import UserOut
from app.database import get_db
from app.llm import gateway
from app.llm.providers import ProviderUnavailableError
from app.memory.audit import AuditLogger
from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.extractor import extract_state_with_source
from app.memory.handle import generate_handle
from app.memory.retriever import retrieve_minimum
from app.memory.storage import MemoryStore
from app.memory.versioning import evolve_state
from app.security import CHAT_LIMIT, limiter, user_or_ip

import json

router = APIRouter(tags=["memory"])


def _store(db: Session) -> MemoryStore:
    return MemoryStore(db.get_bind())


def _audit(db: Session) -> AuditLogger:
    return AuditLogger(db.get_bind())


class IngestRequest(BaseModel):
    session_tag: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1)


class QueryRequest(BaseModel):
    session_tag: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1)
    # Zero-key instant demo: when true, the disclosure is written to the
    # audit trail (provider "demo") so the demo exercises the full pipeline
    # without ever touching /chat or needing a provider key.
    audit: bool = False


class ChatRequest(QueryRequest):
    model: str = Field(default="openai/gpt-4o-mini", max_length=100)
    provider: str = Field(default="openrouter", max_length=50)


@router.post("/memory/ingest")
def ingest(
    body: IngestRequest,
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    store = _store(db)
    extracted_state, extraction_source = extract_state_with_source(body.text)
    extracted = extracted_state.model_dump()

    parent_handle = store.get_latest_handle(user.id, body.session_tag)
    if parent_handle is not None:
        old_row = store.get_state(parent_handle)
        new_state, handle = evolve_state(old_row["state_json"], extracted, parent_handle)
        new_state.pop("parent_handle", None)  # lineage lives in the column
    else:
        new_state = json.loads(canonicalize(extracted))
        handle = generate_handle(
            canonicalize(extracted), SCHEMA_VERSION, NORM_VERSION
        )

    store.save_state(
        handle, parent_handle, new_state, SCHEMA_VERSION, NORM_VERSION,
        user_id=user.id, session_tag=body.session_tag,
    )
    return {
        "handle": handle,
        "parent_handle": parent_handle,
        "state": new_state,
        "conflicts": new_state.get("conflicts", []),
        # metadata only — deliberately outside `state`, so it never
        # reaches canonicalization and cannot change the handle
        "extraction_source": extraction_source,
    }


def _query_subset(
    db: Session, user_id: int, session_tag: str, query: str
) -> tuple[str, dict[str, Any]]:
    store = _store(db)
    handle = store.get_latest_handle(user_id, session_tag)
    if handle is None:
        # cross-session consistency (module 9): fall back to the user's
        # newest state from any prior session
        handle = store.get_latest_handle(user_id)
    if handle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no state for this user")
    state = store.get_state(handle)["state_json"]
    return handle, retrieve_minimum(query, state)


@router.post("/memory/query")
def query(
    body: QueryRequest,
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    handle, result = _query_subset(db, user.id, body.session_tag, body.query)
    audit_id = None
    if body.audit:
        audit_id = uuid.uuid4().hex
        _audit(db).log_response(
            request_id=audit_id,
            user_id=user.id,
            handle_used=handle,
            subset_keys=result["metadata"]["subset_keys"],
            provider="demo",
            model="scripted-demo",
            schema_version=SCHEMA_VERSION,
            norm_version=NORM_VERSION,
            session_tag=body.session_tag,
        )
    return {
        "handle_used": handle,
        "subset": result["subset"],
        "metadata": result["metadata"],
        "audit_id": audit_id,
    }


@router.post("/chat")
# per user, not per IP: this endpoint spends the user's provider credit, and
# an office behind one NAT must not share a single budget
@limiter.limit(CHAT_LIMIT, key_func=user_or_ip)
def chat(
    request: Request,
    body: ChatRequest,
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    handle, result = _query_subset(db, user.id, body.session_tag, body.query)
    system_context = gateway.build_system_context(handle, result["subset"])
    # the model id can override the requested provider (e.g. ollama/*), so
    # error messages must name the provider that actually handled the call
    served_by = gateway.resolve_provider(body.model, body.provider)

    try:
        llm_result = gateway.chat(
            db, user.id, body.model, system_context, body.query, body.provider
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except NotImplementedError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc))
    except ProviderUnavailableError as exc:
        # already written for the end user (e.g. "is `ollama serve` running?")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    except httpx.TimeoutException:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Provider error: {served_by} timed out — try again.",
        )
    except httpx.HTTPStatusError as exc:
        reason = f"{served_by} returned HTTP {exc.response.status_code}"
        try:  # surface the provider's own message when it sends one
            err = exc.response.json()["error"]
            if isinstance(err, str):
                # Ollama: {"error": "model requires more system memory (…)"}
                reason = err
            else:
                # OpenRouter: {"error": {"message": …, "metadata": {"raw": …}}}
                reason = err["message"]
                raw = (err.get("metadata") or {}).get("raw")
                if isinstance(raw, str) and raw and raw not in reason:
                    reason = f"{reason} — {raw[:300]}"
        except Exception:  # noqa: BLE001 — any shape of error body
            pass
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Provider error: {reason}")
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Provider error: could not reach {served_by} ({exc.__class__.__name__}).",
        )

    request_id = uuid.uuid4().hex
    _audit(db).log_response(
        request_id=request_id,
        user_id=user.id,
        handle_used=handle,
        subset_keys=result["metadata"]["subset_keys"],
        # the gateway may route by model id (e.g. ollama/*), so trust the
        # provider that actually served the call over the requested one
        provider=llm_result.get("provider", body.provider),
        model=llm_result["model"],
        schema_version=SCHEMA_VERSION,
        norm_version=NORM_VERSION,
        session_tag=body.session_tag,
    )
    return {
        "response": llm_result["content"],
        "handle_used": handle,
        "subset_keys": result["metadata"]["subset_keys"],
        "audit_id": request_id,
    }


@router.get("/memory/stats")
def stats(
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dashboard summary: counts, latest handles, and token-saved estimate."""
    from sqlalchemy import func, select

    from app.memory.audit import audit_logs
    from app.memory.storage import memory_states as ms

    session_count = db.execute(
        select(func.count(func.distinct(ms.c.session_tag))).where(ms.c.user_id == user.id)
    ).scalar_one()
    state_count = db.execute(
        select(func.count()).select_from(ms).where(ms.c.user_id == user.id)
    ).scalar_one()
    audit_count = db.execute(
        select(func.count()).select_from(audit_logs).where(audit_logs.c.user_id == user.id)
    ).scalar_one()
    latest = db.execute(
        select(ms.c.handle, ms.c.session_tag, ms.c.created_at)
        .where(ms.c.user_id == user.id)
        .order_by(ms.c.created_at.desc())
        .limit(8)
    ).mappings().all()

    # token-saved estimate: replay the most recent audited request and
    # compare subset size vs full state size (retriever metadata basis)
    token_saved_pct = None
    last_req = db.execute(
        select(audit_logs.c.request_id)
        .where(audit_logs.c.user_id == user.id)
        .order_by(audit_logs.c.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last_req:
        replayed = _audit(db).replay(last_req)
        if replayed:
            full = _store(db).get_state(replayed["handle_used"])
            if full:
                full_len = len(json.dumps(full["state_json"], ensure_ascii=False))
                sub_len = len(json.dumps(replayed["subset"], ensure_ascii=False))
                if full_len:
                    token_saved_pct = round(100 * (1 - sub_len / full_len), 1)

    return {
        "session_count": session_count,
        "state_count": state_count,
        "audit_count": audit_count,
        "token_saved_pct": token_saved_pct,
        "latest_handles": [
            {
                "handle": r["handle"],
                "session_tag": r["session_tag"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in latest
        ],
    }


@router.get("/memory/state/{handle}")
def state_by_handle(
    handle: str,
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Inspect any state in the user's version chain by its handle."""
    row = _store(db).get_state(handle, user_id=user.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown handle")
    return {
        "handle": row["handle"],
        "parent_handle": row["parent_handle"],
        "state": row["state_json"],
        "session_tag": row["session_tag"],
        "created_at": row["created_at"].isoformat(),
    }


@router.get("/memory/versions")
def versions(
    session_tag: str,
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {"session_tag": session_tag, "versions": _store(db).list_versions(user.id, session_tag)}


@router.get("/audit")
def audit_trail(
    limit: int = 50,
    session_tag: str | None = None,
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    entries = _audit(db).get_audit_trail(user.id, limit=limit, session_tag=session_tag)
    for e in entries:
        e["created_at"] = e["created_at"].isoformat()
    return {"entries": entries}


# --- developer API usage ------------------------------------------------------

# Rough chars-per-token for English + JSON; good enough for an estimate and
# stated as such, rather than pretending to a tokenizer's precision.
_CHARS_PER_TOKEN = 4


@router.get("/usage")
def usage(
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Account usage for the developer API.

    `est_tokens_saved` sums the retriever's work across every audited
    disclosure: for each request, how much smaller the subset actually sent
    was than the full state it came from.
    """
    from datetime import datetime, time, timezone

    from sqlalchemy import func, select

    from app.memory.audit import audit_logs
    from app.memory.storage import memory_states as ms

    midnight_utc = datetime.combine(datetime.now(timezone.utc).date(), time.min)

    requests_today = db.execute(
        select(func.count())
        .select_from(audit_logs)
        .where(audit_logs.c.user_id == user.id)
        .where(audit_logs.c.created_at >= midnight_utc)
    ).scalar_one()
    total_audit_rows = db.execute(
        select(func.count()).select_from(audit_logs).where(audit_logs.c.user_id == user.id)
    ).scalar_one()
    total_states = db.execute(
        select(func.count()).select_from(ms).where(ms.c.user_id == user.id)
    ).scalar_one()

    rows = db.execute(
        select(audit_logs.c.handle_used, audit_logs.c.subset_keys)
        .where(audit_logs.c.user_id == user.id)
        .where(audit_logs.c.handle_used.is_not(None))
    ).mappings().all()

    store = _store(db)
    state_cache: dict[str, dict[str, Any] | None] = {}
    saved_chars = 0
    for row in rows:
        handle = row["handle_used"]
        if handle not in state_cache:  # many requests share one handle
            found = store.get_state(handle, user_id=user.id)
            state_cache[handle] = found["state_json"] if found else None
        state = state_cache[handle]
        if state is None:
            continue
        subset = _subset_from_keys(state, row["subset_keys"] or [])
        full_len = len(json.dumps(state, ensure_ascii=False))
        subset_len = len(json.dumps(subset, ensure_ascii=False))
        saved_chars += max(0, full_len - subset_len)

    return {
        "requests_today": requests_today,
        "total_states": total_states,
        "total_audit_rows": total_audit_rows,
        "est_tokens_saved": saved_chars // _CHARS_PER_TOKEN,
    }


def _subset_from_keys(state: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    """Rebuild the disclosed subset from its dotted keys (audit replay shape)."""
    subset: dict[str, Any] = {}
    for dotted in keys:
        section, _, key = dotted.partition(".")
        container = state.get(section)
        if isinstance(container, dict) and key in container:
            subset.setdefault(section, {})[key] = container[key]
        elif isinstance(container, list):
            matches = [e for e in container if isinstance(e, dict) and e.get("field") == key]
            if matches:
                subset.setdefault(section, []).extend(matches)
    return subset
