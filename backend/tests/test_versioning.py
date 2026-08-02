"""Tests for append-only versioning and conflict detection."""

import copy

import pytest
from sqlalchemy import create_engine

from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.conflict import detect_conflicts
from app.memory.handle import generate_handle
from app.memory.storage import MemoryStore, metadata
from app.memory.versioning import evolve_state

OLD_STATE = {
    "facts": {"name": "Ayaan"},
    "preferences": {"contact_mode": "email"},
    "constraints": {"budget": {"max": {"value": 2000, "currency": "INR"}}},
    "unresolved": [{"field": "delivery_time", "reason": "not provided"}],
    "conflicts": [],
}


def _handle_of(state: dict) -> str:
    return generate_handle(canonicalize(state), SCHEMA_VERSION, NORM_VERSION)


def test_budget_update_creates_new_handle_old_still_retrievable() -> None:
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    store = MemoryStore(engine)

    old_handle = _handle_of(OLD_STATE)
    store.save_state(old_handle, None, OLD_STATE, "v1", "v1", user_id=1, session_tag="s1")

    new_state, new_handle = evolve_state(
        OLD_STATE, {"constraints": {"budget": {"max": {"value": 2500, "currency": "INR"}}}}, old_handle
    )
    assert new_handle != old_handle
    store.save_state(new_handle, old_handle, new_state, "v1", "v1", user_id=1, session_tag="s1")

    # old record untouched, old value still retrievable
    old_row = store.get_state(old_handle)
    assert old_row is not None
    assert old_row["state_json"]["constraints"]["budget"]["max"]["value"] == 2000
    # new record has new value and lineage
    new_row = store.get_state(new_handle)
    assert new_row["state_json"]["constraints"]["budget"]["max"]["value"] == 2500
    assert new_row["parent_handle"] == old_handle
    assert store.list_versions(1, "s1") == [old_handle, new_handle]


def test_contact_change_produces_conflict_entry() -> None:
    new_state, _ = evolve_state(
        OLD_STATE, {"preferences": {"contact_mode": "call"}}, _handle_of(OLD_STATE)
    )
    assert new_state["preferences"]["contact_mode"] == "call"  # updated, not blocked
    conflicts = new_state["conflicts"]
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["field"] == "preferences.contact_mode"
    assert c["old"] == "email"
    assert c["new"] == "call"
    assert "timestamp" in c


def test_detect_conflicts_ignores_new_and_unchanged_fields() -> None:
    conflicts = detect_conflicts(
        OLD_STATE,
        {"facts": {"name": "Ayaan", "city": "Pune"}, "preferences": {"contact_mode": "email"}},
    )
    assert conflicts == []


def test_evolve_does_not_mutate_old_state() -> None:
    snapshot = copy.deepcopy(OLD_STATE)
    evolve_state(OLD_STATE, {"constraints": {"budget": {"max": {"value": 9999, "currency": "INR"}}}}, "shm_" + "a" * 40)
    assert OLD_STATE == snapshot


def test_resolved_unresolved_entry_is_dropped() -> None:
    new_state, _ = evolve_state(
        OLD_STATE, {"constraints": {"delivery_time": "2026-07-10"}}, _handle_of(OLD_STATE)
    )
    assert all(u["field"] != "delivery_time" for u in new_state.get("unresolved", []))


def test_same_update_is_deterministic() -> None:
    # non-conflicting update: no timestamped conflict entry, so handles must match
    update = {"facts": {"city": "Pune"}}
    _, h1 = evolve_state(OLD_STATE, update, "shm_" + "a" * 40)
    _, h2 = evolve_state(OLD_STATE, update, "shm_" + "a" * 40)
    assert h1 == h2


# --- accumulating (list-valued) fields ----------------------------------------
# The extractor can collect a field rather than replace it, e.g. the
# requirements it gathers across a conversation. Those must union, not
# overwrite: a later message adding one requirement must not drop the rest.


def test_list_fields_accumulate_across_turns() -> None:
    old = {**OLD_STATE, "constraints": {
        "budget": {"max": {"value": 2000, "currency": "INR"}}, "requirements": ["SOC2 compliant"],
    }}
    new_state, _ = evolve_state(
        old, {"constraints": {"requirements": ["SSO support"]}}, _handle_of(old)
    )
    assert new_state["constraints"]["requirements"] == ["SOC2 compliant", "SSO support"]
    # the scalar alongside it is untouched
    assert new_state["constraints"]["budget"]["max"]["value"] == 2000


def test_list_union_is_deduped_and_sorted() -> None:
    old = {**OLD_STATE, "constraints": {"requirements": ["SSO support"]}}
    new_state, _ = evolve_state(
        old,
        {"constraints": {"requirements": ["SSO support", "99.9% uptime"]}},
        _handle_of(old),
    )
    assert new_state["constraints"]["requirements"] == ["99.9% uptime", "SSO support"]


def test_list_arrival_order_does_not_change_the_handle() -> None:
    """Two users stating the same requirements in either order must converge."""
    base = {**OLD_STATE, "constraints": {"requirements": ["SOC2 compliant"]}}
    _, h1 = evolve_state(
        base, {"constraints": {"requirements": ["SSO support", "audit log"]}},
        "shm_" + "a" * 40,
    )
    _, h2 = evolve_state(
        base, {"constraints": {"requirements": ["audit log", "SSO support"]}},
        "shm_" + "a" * 40,
    )
    assert h1 == h2


def test_growing_a_list_is_not_a_conflict() -> None:
    """A longer list is more information, not a contradiction — and a spurious
    conflict record would stamp a wall-clock time into the state."""
    old = {**OLD_STATE, "constraints": {"requirements": ["SOC2 compliant"]}}
    conflicts = detect_conflicts(
        old, {"constraints": {"requirements": ["SSO support"]}}
    )
    assert conflicts == []

    new_state, _ = evolve_state(
        old, {"constraints": {"requirements": ["SSO support"]}}, _handle_of(old)
    )
    # canonicalization drops empty lists, so an absent key means "none recorded"
    assert new_state.get("conflicts", []) == []


def test_scalar_replacing_a_list_still_conflicts() -> None:
    """Only list-vs-list accumulates; a type change is still a real change."""
    old = {**OLD_STATE, "constraints": {"requirements": ["SOC2 compliant"]}}
    conflicts = detect_conflicts(old, {"constraints": {"requirements": "none"}})
    assert [c["field"] for c in conflicts] == ["constraints.requirements"]
