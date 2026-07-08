"""Audit logging and deterministic replay for StateJar.

Every LLM response is logged with the exact handle + subset of state
that was disclosed, so any past response context can be reconstructed
byte-for-byte. Secrets (provider keys, passwords, tokens) are never
logged: log_response scrubs its inputs before writing.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    select,
)
from sqlalchemy.engine import Engine

from app.memory.storage import MemoryStore

audit_metadata = MetaData()

audit_logs = Table(
    "audit_logs",
    audit_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("request_id", String(64), nullable=False),
    Column("user_id", Integer, nullable=False),
    Column("handle_used", String(80), nullable=True),
    Column("session_tag", String(100), nullable=True),
    Column("subset_keys", JSON, nullable=True),
    Column("provider", String(50), nullable=True),
    Column("model", String(100), nullable=True),
    Column("schema_version", String(20), nullable=True),
    Column("norm_version", String(20), nullable=True),
    Column("created_at", DateTime, nullable=False),
)


class SecretInAuditError(ValueError):
    """Raised when a value passed to the audit logger looks like a secret."""


# key names that must never appear in audit payloads
_SECRET_KEY_NAMES = re.compile(
    r"(?:^|[._-])(?:password|passwd|secret|api[_-]?key|provider[_-]?key|token|credential)s?(?:$|[._-])",
    re.IGNORECASE,
)
# values that look like raw secrets/keys
_SECRET_VALUE_RE = re.compile(
    r"^(?:sk-|pk-|rk-|Bearer\s|ghp_|xox[bap]-|AKIA)[\w\-\.]+", re.IGNORECASE
)


def _scrub(value: Any, path: str = "") -> None:
    """Raise SecretInAuditError if anything secret-like is present."""
    if isinstance(value, str):
        if _SECRET_VALUE_RE.match(value.strip()):
            raise SecretInAuditError(f"secret-like value at {path or 'input'} refused")
        if _SECRET_KEY_NAMES.search(value):
            raise SecretInAuditError(f"secret-like key name '{value}' refused")
    elif isinstance(value, dict):
        for k, v in value.items():
            if _SECRET_KEY_NAMES.search(str(k)):
                raise SecretInAuditError(f"secret-like key '{k}' refused")
            _scrub(v, f"{path}.{k}" if path else str(k))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _scrub(item, f"{path}[{i}]")


class AuditLogger:
    """Writes and reads the audit_logs table; supports deterministic replay."""

    def __init__(self, engine: Engine, store: MemoryStore | None = None) -> None:
        self._engine = engine
        self._store = store or MemoryStore(engine)

    def log_response(
        self,
        request_id: str,
        user_id: int,
        handle_used: str | None,
        subset_keys: list[str] | None,
        provider: str | None,
        model: str | None,
        schema_version: str | None,
        norm_version: str | None,
        session_tag: str | None = None,
    ) -> None:
        """Record which handle + state subset backed a response.

        All inputs are scrubbed: provider keys, passwords, or raw secrets
        are refused outright rather than stored.
        """
        _scrub(subset_keys, "subset_keys")
        for name, val in (("provider", provider), ("model", model), ("session_tag", session_tag)):
            _scrub(val, name)

        with self._engine.begin() as conn:
            conn.execute(
                audit_logs.insert().values(
                    request_id=request_id,
                    user_id=user_id,
                    handle_used=handle_used,
                    session_tag=session_tag,
                    subset_keys=subset_keys,
                    provider=provider,
                    model=model,
                    schema_version=schema_version,
                    norm_version=norm_version,
                    created_at=datetime.now(timezone.utc),
                )
            )

    def get_audit_trail(
        self, user_id: int, limit: int = 50, session_tag: str | None = None
    ) -> list[dict[str, Any]]:
        """Newest-first audit entries for a user, optionally one session's only."""
        stmt = (
            select(audit_logs)
            .where(audit_logs.c.user_id == user_id)
            .order_by(audit_logs.c.created_at.desc(), audit_logs.c.id.desc())
            .limit(limit)
        )
        if session_tag is not None:
            stmt = stmt.where(audit_logs.c.session_tag == session_tag)
        with self._engine.connect() as conn:
            return [dict(r) for r in conn.execute(stmt).mappings()]

    def replay(self, request_id: str) -> dict[str, Any] | None:
        """Reconstruct exactly which handle + subset was used for a request.

        Fetches the state by its handle and re-applies subset_keys to
        rebuild the disclosed subset. Returns None if the request or its
        state is unknown.
        """
        stmt = select(audit_logs).where(audit_logs.c.request_id == request_id)
        with self._engine.connect() as conn:
            entry = conn.execute(stmt).mappings().first()
        if entry is None or not entry["handle_used"]:
            return None

        row = self._store.get_state(entry["handle_used"])
        if row is None:
            return None
        state: dict[str, Any] = row["state_json"]

        subset: dict[str, Any] = {}
        for dotted in entry["subset_keys"] or []:
            section, _, key = dotted.partition(".")
            container = state.get(section)
            if isinstance(container, dict) and key in container:
                subset.setdefault(section, {})[key] = container[key]
            elif isinstance(container, list):  # unresolved/conflicts entries by field
                matches = [
                    e for e in container
                    if isinstance(e, dict) and e.get("field") == key
                ]
                if matches:
                    subset.setdefault(section, []).extend(matches)

        return {
            "request_id": request_id,
            "handle_used": entry["handle_used"],
            "subset_keys": entry["subset_keys"],
            "subset": subset,
            "provider": entry["provider"],
            "model": entry["model"],
            "schema_version": entry["schema_version"],
            "norm_version": entry["norm_version"],
        }
