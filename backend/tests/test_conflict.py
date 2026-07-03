"""Tests for conflict detection (app.memory.conflict)."""

from app.memory.conflict import detect_conflicts

OLD_STATE = {
    "facts": {"name": "Ayaan"},
    "preferences": {"contact_mode": "email"},
    "constraints": {"budget_inr_max": 2000},
    "conflicts": [],
}


def test_changed_value_is_a_conflict() -> None:
    conflicts = detect_conflicts(OLD_STATE, {"preferences": {"contact_mode": "call"}})
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["field"] == "preferences.contact_mode"
    assert c["old"] == "email"
    assert c["new"] == "call"
    assert "timestamp" in c


def test_new_field_is_not_a_conflict() -> None:
    assert detect_conflicts(OLD_STATE, {"facts": {"city": "Pune"}}) == []


def test_unchanged_value_is_not_a_conflict() -> None:
    assert detect_conflicts(OLD_STATE, {"preferences": {"contact_mode": "email"}}) == []


def test_multiple_conflicts_detected() -> None:
    conflicts = detect_conflicts(
        OLD_STATE,
        {"preferences": {"contact_mode": "whatsapp"}, "constraints": {"budget_inr_max": 2500}},
    )
    fields = {c["field"] for c in conflicts}
    assert fields == {"preferences.contact_mode", "constraints.budget_inr_max"}


def test_empty_new_extracted_yields_no_conflicts() -> None:
    assert detect_conflicts(OLD_STATE, {}) == []
