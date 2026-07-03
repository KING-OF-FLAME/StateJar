"""Tests for deterministic state-handle generation."""

from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.handle import generate_handle, verify_handle


def test_same_state_same_handle_100_iterations() -> None:
    canonical = canonicalize({"facts": {"name": "Ayaan"}})
    first = generate_handle(canonical, SCHEMA_VERSION, NORM_VERSION)
    for _ in range(100):
        assert generate_handle(canonical, SCHEMA_VERSION, NORM_VERSION) == first


def test_handle_format() -> None:
    handle = generate_handle("{}", "v1", "v1")
    assert handle.startswith("shm_")
    assert len(handle) == 4 + 40
    assert all(c in "0123456789abcdef" for c in handle[4:])


def test_one_character_change_changes_handle() -> None:
    a = generate_handle('{"facts":{"name":"Ayaan"}}', "v1", "v1")
    b = generate_handle('{"facts":{"name":"Ayaam"}}', "v1", "v1")
    assert a != b


def test_version_change_changes_handle() -> None:
    canonical = '{"facts":{"name":"Ayaan"}}'
    assert generate_handle(canonical, "v1", "v1") != generate_handle(canonical, "v2", "v1")
    assert generate_handle(canonical, "v1", "v1") != generate_handle(canonical, "v1", "v2")


def test_key_order_invariance_via_canonicalizer() -> None:
    a = {"facts": {"name": "Ayaan", "city": "Pune"}, "constraints": {"budget": "₹2,000"}}
    b = {"constraints": {"budget": "2000"}, "facts": {"city": "Pune", "name": "Ayaan"}}
    handle_a = generate_handle(canonicalize(a), SCHEMA_VERSION, NORM_VERSION)
    handle_b = generate_handle(canonicalize(b), SCHEMA_VERSION, NORM_VERSION)
    assert handle_a == handle_b


def test_verify_handle() -> None:
    canonical = canonicalize({"facts": {"name": "Ayaan"}})
    handle = generate_handle(canonical, SCHEMA_VERSION, NORM_VERSION)
    assert verify_handle(canonical, SCHEMA_VERSION, NORM_VERSION, handle)
    assert not verify_handle(canonical, SCHEMA_VERSION, NORM_VERSION, "shm_" + "0" * 40)
    assert not verify_handle(canonical, "v2", NORM_VERSION, handle)
