"""Persistence layer for StateJar memory states.

Backed by the `memory_states` table. Handles are deterministic content
addresses, so duplicate saves are deduplicated with INSERT IGNORE
(MySQL) / INSERT OR IGNORE (SQLite, used in tests).

Patent module 5 — No Full Chat Replay: this module never stores raw
chat transcripts. Any state_json containing a transcript-like key is
rejected before touching the database.
"""

from __future__ import annotations

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

FORBIDDEN_KEYS = {"raw_transcript", "chat_history"}

metadata = MetaData()

memory_states = Table(
    "memory_states",
    metadata,
    Column("handle", String(80), primary_key=True),
    Column("parent_handle", String(80), nullable=True),
    Column("state_json", JSON, nullable=False),
    Column("schema_version", String(20), nullable=False),
    Column("norm_version", String(20), nullable=False),
    Column("user_id", Integer, nullable=False),
    Column("session_tag", String(100), nullable=True),
    Column("created_at", DateTime, nullable=False),
)


class TranscriptNotAllowedError(ValueError):
    """Raised when state_json contains raw chat transcript data."""


def _assert_no_transcript(value: Any) -> None:
    """Recursively reject transcript-like keys anywhere in the state."""
    if isinstance(value, dict):
        for key, sub in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise TranscriptNotAllowedError(
                    f"state_json must not contain '{key}': "
                    "raw transcripts are never stored (No Full Chat Replay)"
                )
            _assert_no_transcript(sub)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_transcript(item)


class MemoryStore:
    """CRUD operations over the memory_states table."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save_state(
        self,
        handle: str,
        parent_handle: str | None,
        state_json: dict[str, Any],
        schema_version: str,
        norm_version: str,
        user_id: int,
        session_tag: str | None = None,
    ) -> bool:
        """Insert a state row; return True if inserted, False if it already existed.

        Deterministic handles make the primary key a natural dedup, so
        collisions are ignored rather than raised.
        """
        _assert_no_transcript(state_json)

        if self._engine.dialect.name == "mysql":
            stmt = memory_states.insert().prefix_with("IGNORE")
        else:  # sqlite and others with OR IGNORE support (tests)
            stmt = memory_states.insert().prefix_with("OR IGNORE")

        with self._engine.begin() as conn:
            result = conn.execute(
                stmt.values(
                    handle=handle,
                    parent_handle=parent_handle,
                    state_json=state_json,
                    schema_version=schema_version,
                    norm_version=norm_version,
                    user_id=user_id,
                    session_tag=session_tag,
                    created_at=datetime.now(timezone.utc),
                )
            )
        return bool(result.rowcount)

    def get_state(self, handle: str) -> dict[str, Any] | None:
        """Return the full row for a handle as a dict, or None if missing."""
        with self._engine.connect() as conn:
            row = conn.execute(
                select(memory_states).where(memory_states.c.handle == handle)
            ).mappings().first()
        return dict(row) if row is not None else None

    def get_latest_handle(self, user_id: int, session_tag: str | None = None) -> str | None:
        """Return the newest handle for a user (optionally scoped to a session)."""
        stmt = (
            select(memory_states.c.handle)
            .where(memory_states.c.user_id == user_id)
            .order_by(memory_states.c.created_at.desc())
            .limit(1)
        )
        if session_tag is not None:
            stmt = stmt.where(memory_states.c.session_tag == session_tag)
        with self._engine.connect() as conn:
            return conn.execute(stmt).scalar_one_or_none()

    def list_versions(self, user_id: int, session_tag: str | None = None) -> list[str]:
        """Return the handle chain for a user/session, oldest first."""
        stmt = (
            select(memory_states.c.handle)
            .where(memory_states.c.user_id == user_id)
            .order_by(memory_states.c.created_at.asc())
        )
        if session_tag is not None:
            stmt = stmt.where(memory_states.c.session_tag == session_tag)
        with self._engine.connect() as conn:
            return list(conn.execute(stmt).scalars())
