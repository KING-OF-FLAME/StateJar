"""Tests for minimal-subset retrieval."""

from app.memory.retriever import classify_intents, retrieve_minimum

AYAAN_STATE = {
    "facts": {"name": "Ayaan", "city": "Pune"},
    "preferences": {"contact_mode": "email", "theme": "dark"},
    "decisions": {"choice": "blue variant"},
    "constraints": {"budget_inr_max": 2000},
    "goals": {"primary": "renovate kitchen"},
    "unresolved": [{"field": "delivery_time", "reason": "not provided"}],
    "conflicts": [],
}


def test_booking_query_returns_only_required_subset() -> None:
    result = retrieve_minimum(
        "Book my delivery with my usual preferences", AYAAN_STATE
    )
    assert result["subset"] == {
        "preferences": {"contact_mode": "email"},
        "constraints": {"budget_inr_max": 2000},
        "unresolved": [{"field": "delivery_time", "reason": "not provided"}],
    }
    # nothing else leaked
    assert "facts" not in result["subset"]
    assert "decisions" not in result["subset"]
    assert "goals" not in result["subset"]


def test_booking_metadata() -> None:
    result = retrieve_minimum("Book my delivery", AYAAN_STATE)
    meta = result["metadata"]
    assert "booking" in meta["intents"]
    assert set(meta["subset_keys"]) == {
        "preferences.contact_mode",
        "constraints.budget_inr_max",
        "unresolved.delivery_time",
    }
    # 8 total fields (7 leaves + 1 unresolved entry), 3 kept
    assert meta["fields_dropped"] == 5
    assert 0 < meta["token_estimate_saved_pct"] < 100


def test_contact_query() -> None:
    result = retrieve_minimum("How should I contact you?", AYAAN_STATE)
    assert result["subset"] == {"preferences": {"contact_mode": "email"}}


def test_budget_query_returns_constraints() -> None:
    result = retrieve_minimum("What's my budget?", AYAAN_STATE)
    assert result["subset"]["constraints"] == {"budget_inr_max": 2000}
    assert "preferences" not in result["subset"]


def test_unrelated_query_returns_empty_subset() -> None:
    result = retrieve_minimum("Tell me a joke", AYAAN_STATE)
    assert result["subset"] == {}
    assert result["metadata"]["intents"] == []
    assert result["metadata"]["subset_keys"] == []


def test_classify_multiple_intents() -> None:
    intents = classify_intents("Book the order within my budget and call me")
    assert "booking" in intents
    assert "budget" in intents
    assert "contact" in intents
