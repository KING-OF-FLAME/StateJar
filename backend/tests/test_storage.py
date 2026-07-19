"""Tests for MemoryStore using an in-memory SQLite fallback."""

import time

import pytest
from sqlalchemy import create_engine

from app.memory.storage import MemoryStore, TranscriptNotAllowedError, metadata


@pytest.fixture
def store() -> MemoryStore:
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    return MemoryStore(engine)


def _save(store: MemoryStore, handle: str, **overrides) -> bool:
    defaults = dict(
        handle=handle,
        parent_handle=None,
        state_json={"facts": {"name": "Ayaan"}},
        schema_version="v1",
        norm_version="v1",
        user_id=1,
        session_tag="s1",
    )
    defaults.update(overrides)
    return store.save_state(**defaults)


def test_save_and_get_state(store: MemoryStore) -> None:
    assert _save(store, "shm_" + "a" * 40) is True
    row = store.get_state("shm_" + "a" * 40)
    assert row is not None
    assert row["state_json"] == {"facts": {"name": "Ayaan"}}
    assert row["schema_version"] == "v1"
    assert row["user_id"] == 1


def test_duplicate_handle_is_deduplicated(store: MemoryStore) -> None:
    assert _save(store, "shm_" + "b" * 40) is True
    assert _save(store, "shm_" + "b" * 40) is False  # ignored, no error
    assert store.list_versions(1, "s1") == ["shm_" + "b" * 40]


def test_get_missing_state_returns_none(store: MemoryStore) -> None:
    assert store.get_state("shm_" + "f" * 40) is None


def test_latest_handle_and_version_chain(store: MemoryStore) -> None:
    h1, h2, h3 = ("shm_" + c * 40 for c in "123")
    _save(store, h1)
    time.sleep(0.002)
    _save(store, h2, parent_handle=h1)
    time.sleep(0.002)
    _save(store, h3, parent_handle=h2)
    assert store.get_latest_handle(1, "s1") == h3
    assert store.list_versions(1, "s1") == [h1, h2, h3]


def test_session_tag_scoping(store: MemoryStore) -> None:
    _save(store, "shm_" + "c" * 40, session_tag="s1")
    time.sleep(0.002)
    _save(store, "shm_" + "d" * 40, session_tag="s2")
    assert store.get_latest_handle(1, "s1") == "shm_" + "c" * 40
    assert store.get_latest_handle(1, "s2") == "shm_" + "d" * 40
    assert store.get_latest_handle(1) == "shm_" + "d" * 40  # unscoped: newest overall
    assert store.get_latest_handle(2) is None


def test_transcript_keys_rejected(store: MemoryStore) -> None:
    with pytest.raises(TranscriptNotAllowedError):
        _save(store, "shm_" + "e" * 40, state_json={"raw_transcript": "hi there"})
    with pytest.raises(TranscriptNotAllowedError):
        _save(store, "shm_" + "e" * 40, state_json={"facts": {"chat_history": ["hi"]}})
    # nested inside a list too
    with pytest.raises(TranscriptNotAllowedError):
        _save(
            store,
            "shm_" + "e" * 40,
            state_json={"items": [{"RAW_TRANSCRIPT": "x"}]},
        )
    assert store.get_state("shm_" + "e" * 40) is None  # nothing was written


def test_same_handle_different_user_or_session_is_stored(store: MemoryStore) -> None:
    """Content-addressed handles collide across users running identical demos;
    each user/session scope must still get its own row."""
    h = "shm_" + "9" * 40
    assert _save(store, h, user_id=1, session_tag="demo-a") is True
    assert _save(store, h, user_id=2, session_tag="demo-b") is True   # new user
    assert _save(store, h, user_id=1, session_tag="demo-c") is True   # new session
    assert _save(store, h, user_id=1, session_tag="demo-a") is False  # true dup
    assert store.get_latest_handle(2, "demo-b") == h
    assert store.list_versions(1, "demo-c") == [h]
    assert store.get_state(h, user_id=2)["user_id"] == 2
    assert store.get_state(h, user_id=3) is None
