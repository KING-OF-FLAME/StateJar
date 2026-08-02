"""Tests for AuditLogger: logging, trail, replay, and secret scrubbing."""

import json

import pytest
from sqlalchemy import create_engine

from app.memory.audit import AuditLogger, SecretInAuditError, audit_metadata
from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.extractor import extract_state
from app.memory.handle import generate_handle
from app.memory.storage import MemoryStore, metadata as storage_metadata
from app.timeutil import iso_utc

STATE = {
    "facts": {"name": "Ayaan"},
    "preferences": {"contact_mode": "email"},
    "constraints": {"budget_inr_max": 2000},
    "unresolved": [{"field": "delivery_time", "reason": "not provided"}],
}
HANDLE = "shm_" + "a" * 40


@pytest.fixture
def logger() -> AuditLogger:
    engine = create_engine("sqlite:///:memory:")
    storage_metadata.create_all(engine)
    audit_metadata.create_all(engine)
    store = MemoryStore(engine)
    store.save_state(HANDLE, None, STATE, "v1", "v1", user_id=1, session_tag="s1")
    return AuditLogger(engine, store)


def _log(logger: AuditLogger, request_id: str = "req-1", **overrides) -> None:
    defaults = dict(
        request_id=request_id,
        user_id=1,
        handle_used=HANDLE,
        subset_keys=["preferences.contact_mode", "constraints.budget_inr_max",
                     "unresolved.delivery_time"],
        provider="anthropic",
        model="claude-sonnet-4-6",
        schema_version="v1",
        norm_version="v1",
    )
    defaults.update(overrides)
    logger.log_response(**defaults)


def test_log_and_trail(logger: AuditLogger) -> None:
    _log(logger, "req-1")
    _log(logger, "req-2")
    trail = logger.get_audit_trail(user_id=1)
    assert [e["request_id"] for e in trail] == ["req-2", "req-1"]  # newest first
    assert trail[0]["handle_used"] == HANDLE
    assert logger.get_audit_trail(user_id=99) == []


def test_trail_respects_limit(logger: AuditLogger) -> None:
    for i in range(5):
        _log(logger, f"req-{i}")
    assert len(logger.get_audit_trail(user_id=1, limit=3)) == 3


def test_trail_filters_by_session_tag(logger: AuditLogger) -> None:
    _log(logger, "req-1", session_tag="session-1")
    _log(logger, "req-2", session_tag="session-2")
    _log(logger, "req-3")  # legacy row, no session recorded
    assert len(logger.get_audit_trail(user_id=1)) == 3  # no filter → everything
    only_s1 = logger.get_audit_trail(user_id=1, session_tag="session-1")
    assert [e["request_id"] for e in only_s1] == ["req-1"]
    assert only_s1[0]["session_tag"] == "session-1"
    assert logger.get_audit_trail(user_id=1, session_tag="nope") == []


def test_replay_reconstructs_exact_subset(logger: AuditLogger) -> None:
    _log(logger, "req-1")
    result = logger.replay("req-1")
    assert result is not None
    assert result["handle_used"] == HANDLE
    assert result["subset"] == {
        "preferences": {"contact_mode": "email"},
        "constraints": {"budget_inr_max": 2000},
        "unresolved": [{"field": "delivery_time", "reason": "not provided"}],
    }
    assert result["provider"] == "anthropic"


def test_replay_unknown_request_returns_none(logger: AuditLogger) -> None:
    assert logger.replay("no-such-request") is None


def test_secret_key_names_refused(logger: AuditLogger) -> None:
    with pytest.raises(SecretInAuditError):
        _log(logger, subset_keys=["provider_keys.encrypted_key"])
    with pytest.raises(SecretInAuditError):
        _log(logger, subset_keys=["facts.password"])
    assert logger.get_audit_trail(user_id=1) == []  # nothing written


def test_secret_like_values_refused(logger: AuditLogger) -> None:
    with pytest.raises(SecretInAuditError):
        _log(logger, provider="sk-" + "ant-abc123def456")  # shaped like a key on purpose
    with pytest.raises(SecretInAuditError):
        _log(logger, model="Bea" + "rer eyJhbGciOi")  # shaped like a token on purpose
    assert logger.get_audit_trail(user_id=1) == []


# --- provenance replay over HTTP ---------------------------------------------


def test_replay_verifies_the_handle() -> None:
    """A content-addressed handle makes replay a real integrity check."""
    engine = create_engine("sqlite:///:memory:")
    storage_metadata.create_all(engine)
    audit_metadata.create_all(engine)
    store = MemoryStore(engine)
    logger = AuditLogger(engine, store)

    state = extract_state(
        "Stack: React + Tailwind. Dark theme, brand color #E07856."
    ).model_dump()
    canonical = canonicalize(state)
    handle = generate_handle(canonical, SCHEMA_VERSION, NORM_VERSION)
    store.save_state(handle, None, json.loads(canonical), SCHEMA_VERSION, NORM_VERSION,
                     user_id=1, session_tag="s1")
    logger.log_response(
        request_id="req-1", user_id=1, handle_used=handle,
        subset_keys=["decisions.stack", "preferences.brand_color"],
        provider="demo", model="scripted-demo",
        schema_version=SCHEMA_VERSION, norm_version=NORM_VERSION, session_tag="s1",
    )

    out = logger.replay("req-1", user_id=1)
    assert out is not None
    assert out["verified"] is True
    assert out["recomputed_handle"] == handle
    assert out["subset"] == {
        "decisions": {"stack": "React + Tailwind"},
        "preferences": {"brand_color": "#E07856"},
    }
    # only the logged keys are reconstructed — theme was never disclosed
    assert "theme" not in out["subset"].get("preferences", {})


def test_replay_is_scoped_to_the_owner() -> None:
    """An audit row records a disclosure; replaying another user's would repeat it."""
    engine = create_engine("sqlite:///:memory:")
    storage_metadata.create_all(engine)
    audit_metadata.create_all(engine)
    store = MemoryStore(engine)
    logger = AuditLogger(engine, store)

    state = extract_state("Stack: React + Tailwind.").model_dump()
    canonical = canonicalize(state)
    handle = generate_handle(canonical, SCHEMA_VERSION, NORM_VERSION)
    store.save_state(handle, None, json.loads(canonical), SCHEMA_VERSION, NORM_VERSION,
                     user_id=1, session_tag="s1")
    logger.log_response(
        request_id="req-1", user_id=1, handle_used=handle, subset_keys=["decisions.stack"],
        provider="demo", model="m", schema_version=SCHEMA_VERSION,
        norm_version=NORM_VERSION, session_tag="s1",
    )

    assert logger.replay("req-1", user_id=1) is not None
    assert logger.replay("req-1", user_id=2) is None      # not yours
    assert logger.replay("nope", user_id=1) is None


def test_timestamps_carry_an_explicit_utc_offset(logger: AuditLogger) -> None:
    """A bare ISO string is read as local time by browsers, skewing every
    'x minutes ago' by the viewer's offset."""
    from datetime import datetime, timezone

    _log(logger, "req-1")
    created = logger.get_audit_trail(user_id=1)[0]["created_at"]
    assert iso_utc(created).endswith("+00:00")
    # round-trips to an aware datetime, so no client has to guess
    assert datetime.fromisoformat(iso_utc(created)).tzinfo is not None
    assert iso_utc(None) is None
    aware = datetime(2026, 8, 1, 16, 29, tzinfo=timezone.utc)
    assert iso_utc(aware) == iso_utc(aware.replace(tzinfo=None))
