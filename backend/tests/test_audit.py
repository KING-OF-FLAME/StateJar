"""Tests for AuditLogger: logging, trail, replay, and secret scrubbing."""

import pytest
from sqlalchemy import create_engine

from app.memory.audit import AuditLogger, SecretInAuditError, audit_metadata
from app.memory.storage import MemoryStore, metadata as storage_metadata

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
        _log(logger, provider="sk-ant-abc123def456")
    with pytest.raises(SecretInAuditError):
        _log(logger, model="Bearer eyJhbGciOi")
    assert logger.get_audit_trail(user_id=1) == []
