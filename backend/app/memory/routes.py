"""StateJar pipeline routes: ingest → version → retrieve → chat → audit."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.routes import UserOut, get_current_user
from app.database import get_db
from app.llm import gateway
from app.memory.audit import AuditLogger
from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.extractor import extract_state
from app.memory.handle import generate_handle
from app.memory.retriever import retrieve_minimum
from app.memory.storage import MemoryStore
from app.memory.versioning import evolve_state

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


class ChatRequest(QueryRequest):
    model: str = Field(default="openai/gpt-4o-mini", max_length=100)
    provider: str = Field(default="openrouter", max_length=50)


@router.post("/memory/ingest")
def ingest(
    body: IngestRequest,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    store = _store(db)
    extracted = extract_state(body.text).model_dump()

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
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    handle, result = _query_subset(db, user.id, body.session_tag, body.query)
    return {
        "handle_used": handle,
        "subset": result["subset"],
        "metadata": result["metadata"],
    }


@router.post("/chat")
def chat(
    body: ChatRequest,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    handle, result = _query_subset(db, user.id, body.session_tag, body.query)
    system_context = gateway.build_system_context(handle, result["subset"])

    try:
        llm_result = gateway.chat(
            db, user.id, body.model, system_context, body.query, body.provider
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except NotImplementedError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc))

    request_id = uuid.uuid4().hex
    _audit(db).log_response(
        request_id=request_id,
        user_id=user.id,
        handle_used=handle,
        subset_keys=result["metadata"]["subset_keys"],
        provider=body.provider,
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
    user: UserOut = Depends(get_current_user),
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
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Inspect any state in the user's version chain by its handle."""
    row = _store(db).get_state(handle)
    if row is None or row["user_id"] != user.id:
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
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {"session_tag": session_tag, "versions": _store(db).list_versions(user.id, session_tag)}


@router.get("/audit")
def audit_trail(
    limit: int = 50,
    session_tag: str | None = None,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    entries = _audit(db).get_audit_trail(user.id, limit=limit, session_tag=session_tag)
    for e in entries:
        e["created_at"] = e["created_at"].isoformat()
    return {"entries": entries}
