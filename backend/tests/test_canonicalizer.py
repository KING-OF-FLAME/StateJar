"""Tests for canonical state representation."""

import json

from app.memory.canonicalizer import canonicalize


def test_key_order_does_not_matter() -> None:
    a = {"facts": {"name": "Ayaan", "city": "Pune"}, "preferences": {"contact_mode": "email"}}
    b = {"preferences": {"contact_mode": "email"}, "facts": {"city": "Pune", "name": "Ayaan"}}
    assert canonicalize(a) == canonicalize(b)


def test_budget_currency_forms_are_identical() -> None:
    a = {"constraints": {"budget": "₹2,000"}}
    b = {"constraints": {"budget": "2000"}}
    assert canonicalize(a) == canonicalize(b)
    assert json.loads(canonicalize(a))["constraints"]["budget"] == 2000


def test_whitespace_and_enum_normalization() -> None:
    a = {"preferences": {"contact_mode": "  Email  "}, "facts": {"name": "Ayaan  Khan"}}
    canon = json.loads(canonicalize(a))
    assert canon["preferences"]["contact_mode"] == "email"
    assert canon["facts"]["name"] == "Ayaan Khan"


def test_empty_values_removed_and_versions_attached() -> None:
    state = {
        "facts": {"name": "Ayaan"},
        "preferences": {},
        "decisions": {},
        "unresolved": [],
        "conflicts": [],
        "goals": {"note": "   "},
    }
    canon = json.loads(canonicalize(state))
    assert canon == {
        "facts": {"name": "Ayaan"},
        "schema_version": "v1",
        "norm_version": "v1",
    }


def test_date_normalized_to_iso() -> None:
    canon = json.loads(canonicalize({"constraints": {"deadline": "5 July 2026"}}))
    assert canon["constraints"]["deadline"] == "2026-07-05"


def test_output_is_deterministic_compact_json() -> None:
    canon = canonicalize({"facts": {"b": "2", "a": "1"}})
    assert canon == '{"facts":{"a":1,"b":2},"norm_version":"v1","schema_version":"v1"}'
