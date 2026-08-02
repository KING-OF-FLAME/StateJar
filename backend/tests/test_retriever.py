"""Tests for minimal-subset retrieval."""

import json
from collections.abc import Generator

import pytest

from app.config import get_settings
from app.memory.retriever import classify_intents, retrieve_minimum


@pytest.fixture(autouse=True)
def _selective(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Force selective retrieval on.

    These fixtures are all well under the full-state threshold, so with the
    shipped default they would be returned whole and this file would stop
    testing selection at all. Minimal disclosure is the patent claim; it needs
    coverage regardless of what the size fallback is tuned to.
    """
    monkeypatch.setenv("RETRIEVER_FULL_STATE_TOKENS", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


AYAAN_STATE = {
    "facts": {"name": "Ayaan", "city": "Pune"},
    "preferences": {"contact_mode": "email", "theme": "dark"},
    "decisions": {"choice": "blue variant"},
    "constraints": {"budget": {"max": {"value": 2000, "currency": "INR"}}},
    "goals": {"primary": "renovate kitchen"},
    "unresolved": [{"field": "delivery_time", "reason": "not provided"}],
    "conflicts": [],
}


def test_booking_query_returns_only_required_subset() -> None:
    """A booking query that does NOT invoke saved state stays narrow."""
    result = retrieve_minimum("Book my delivery", AYAAN_STATE)
    assert result["subset"] == {
        "preferences": {"contact_mode": "email"},
        "constraints": {"budget": {"max": {"value": 2000, "currency": "INR"}}},
        "unresolved": [{"field": "delivery_time", "reason": "not provided"}],
    }
    # nothing else leaked
    assert "facts" not in result["subset"]
    assert "decisions" not in result["subset"]
    assert "goals" not in result["subset"]


@pytest.mark.parametrize("query", [
    "Book my delivery using my saved preferences",
    "Book my delivery with my usual preferences",
    "order the same as last time",
    "book it as usual",
    "use my profile",
])
def test_asking_for_saved_state_returns_the_whole_namespace(query: str) -> None:
    """BUG-4: "saved preferences" returned 3 of 12 fields.

    The phrase names a namespace, not a keyword to score. Answering it from a
    third of what is known is the failure mode minimal disclosure must not
    have — the point of remembering is to be able to recall.
    """
    result = retrieve_minimum(query, AYAAN_STATE)
    subset = result["subset"]
    assert subset["preferences"] == {"contact_mode": "email", "theme": "dark"}
    assert subset["facts"] == {"name": "Ayaan", "city": "Pune"}
    assert subset["constraints"]["budget"]["max"]["value"] == 2000
    assert subset["goals"] == {"primary": "renovate kitchen"}


def test_conflicts_are_never_disclosed() -> None:
    """A conflict record carries the SUPERSEDED value — the stale figure."""
    state = {
        **AYAAN_STATE,
        "conflicts": [{"field": "constraints.budget.max",
                       "old": {"value": 75000}, "new": {"value": 2000}}],
    }
    for query in ("what is my budget?", "use my saved preferences", "anything"):
        result = retrieve_minimum(query, state)
        assert "conflicts" not in result["subset"], query
        assert "75000" not in json.dumps(result["subset"]), query


def test_booking_metadata() -> None:
    result = retrieve_minimum("Book my delivery", AYAAN_STATE)
    meta = result["metadata"]
    assert "booking" in meta["intents"]
    assert set(meta["subset_keys"]) == {
        "preferences.contact_mode",
        "constraints.budget.max",
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
    assert result["subset"]["constraints"] == {"budget": {"max": {"value": 2000, "currency": "INR"}}}
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
