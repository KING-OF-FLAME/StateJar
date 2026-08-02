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
from app.llm.providers import ProviderError
from app.memory.audit import AuditLogger
from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.extractor import extract
from app.memory.handle import generate_handle
from app.memory.retriever import retrieve_minimum
from app.memory.storage import MemoryStore
from app.memory.versioning import evolve_state
from app.security import CHAT_LIMIT, limiter, user_or_ip
from app.timeutil import iso_utc

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


class ManualAuditIn(BaseModel):
    """A disclosure made by the client rather than by this server."""

    session_tag: str = Field(min_length=1, max_length=100)
    handle_used: str = Field(min_length=4, max_length=80)
    subset_keys: list[str] = Field(default_factory=list)
    provider: str = Field(default="ollama", max_length=50)
    model: str = Field(default="", max_length=100)


class ChatRequest(QueryRequest):
    # Explicitly namespaced: a bare "openai/gpt-4o-mini" is a valid OpenRouter
    # id *and* an OpenAI routing prefix, so the default spells out which one it
    # means rather than depending on precedence.
    model: str = Field(default="openrouter/openai/gpt-4o-mini", max_length=100)
    provider: str = Field(default="openrouter", max_length=50)


@router.post("/memory/ingest")
def ingest(
    body: IngestRequest,
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    store = _store(db)
    extraction = extract(body.text, db=db, user_id=user.id)
    extracted = extraction.state.model_dump()

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
        # metadata only — deliberately outside `state`, so neither the tier
        # list nor the per-field origins can reach canonicalization or move
        # the handle
        "extraction_source": extraction.sources,
        "extraction_origins": extraction.origins,
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
    except ProviderError as exc:
        # already normalised and written for the end user by the provider
        # adapter (bad key, rate limit, unknown model, daemon down) — and the
        # credential is scrubbed there, so it is safe to surface verbatim
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
        # a model that answered in the context's JSON format instead of
        # prose must not have that dumped into the chat bubble
        "response": gateway.clean_reply(llm_result["content"]),
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
                "created_at": iso_utc(r["created_at"]),
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
        "created_at": iso_utc(row["created_at"]),
    }


@router.get("/memory/versions")
def versions(
    session_tag: str,
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {"session_tag": session_tag, "versions": _store(db).list_versions(user.id, session_tag)}


@router.get("/audit/{request_id}/replay")
def audit_replay(
    request_id: str,
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reconstruct exactly what was disclosed for one audited response.

    `verified` re-derives the handle from the stored state: because the
    handle is a SHA-256 content address, a match proves the bytes behind
    that answer are unchanged since it was logged.
    """
    replayed = _audit(db).replay(request_id, user_id=user.id)
    if replayed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown request id")
    return replayed


def _disclosure_note(entry: dict[str, Any]) -> str | None:
    """Why an entry disclosed nothing.

    "nothing disclosed" on its own reads like a bug. It is almost always one
    of two ordinary situations, and saying which is the difference between a
    trustworthy trail and a confusing one.
    """
    if entry.get("subset_keys"):
        return None
    if not entry.get("handle_used"):
        return "no memory existed yet — nothing had been stored for this user"
    return (
        "the query matched no stored field — retrieval is minimal by design, "
        "so an unrelated question discloses nothing"
    )


@router.post("/audit/manual", status_code=status.HTTP_201_CREATED)
def audit_manual(
    body: ManualAuditIn,
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record a disclosure StateJar's server did not make itself.

    Browser-direct local models never touch this backend — the prompt goes
    straight from the user's browser to their own Ollama daemon, which is the
    whole point. The retrieval still happened here, so the audit trail would
    otherwise have a hole exactly where the privacy story is strongest.

    The handle and subset keys are re-verified against what this user
    actually owns, so a client cannot invent provenance.
    """
    store = _store(db)
    row = store.get_state(body.handle_used, user_id=user.id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "unknown handle for this user"
        )
    known = set(_subset_from_keys(row["state_json"], body.subset_keys))
    state = row["state_json"]
    verified = [
        key for key in body.subset_keys
        if key.partition(".")[0] in state or key.partition(".")[0] in known
    ]

    request_id = uuid.uuid4().hex
    _audit(db).log_response(
        request_id=request_id,
        user_id=user.id,
        handle_used=body.handle_used,
        subset_keys=verified,
        provider=body.provider,
        model=body.model,
        schema_version=SCHEMA_VERSION,
        norm_version=NORM_VERSION,
        session_tag=body.session_tag,
    )
    return {"audit_id": request_id, "subset_keys": verified}


@router.get("/audit/facets")
def audit_facets(
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Values that actually appear in this user's trail, for the filter bar."""
    logger = _audit(db)
    return {
        "providers": logger.list_providers(user.id),
        "sessions": logger.list_sessions(user.id),
    }


@router.get("/audit")
def audit_trail(
    limit: int = 50,
    offset: int = 0,
    session_tag: str | None = None,
    provider: str | None = None,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    include_demo: bool = True,
    user: UserOut = Depends(get_api_caller),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    logger = _audit(db)
    bounds = {"since": _parse_dt(since), "until": _parse_dt(until)}
    filters = dict(
        session_tag=session_tag, provider=provider, search=search,
        include_demo=include_demo, **bounds,
    )
    entries = logger.get_audit_trail(
        user.id, limit=min(limit, 200), offset=max(offset, 0), **filters
    )
    for entry in entries:
        entry["created_at"] = iso_utc(entry["created_at"])
        entry["is_demo"] = entry.get("provider") == "demo"
        entry["disclosure_note"] = _disclosure_note(entry)
    total = logger.count_audit_trail(user.id, **filters)
    return {
        "entries": entries,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(entries) < total,
    }


def _parse_dt(value: str | None) -> Any:
    """An ISO date or datetime from a query string, or None."""
    if not value:
        return None
    from datetime import datetime

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


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
