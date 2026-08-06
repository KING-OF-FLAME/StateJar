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


# --- field-name matching ------------------------------------------------------
#
# INTENT_FIELD_MAP is a fixed keyword list built around shopping and code
# briefs. In any other domain it scores zero, selection falls through, and the
# whole state is disclosed on every turn. These cover the layer that reads the
# state's own field names instead, which is what lets selection engage in a
# domain nobody wrote keywords for.

RELIEF_STATE = {
    "facts": {"name": "Meera Nair", "email": "meera@reliefnet.org"},
    "constraints": {
        "budget": {"max": {"value": 2200000, "currency": "INR"}},
        "deadline": {"iso": "2026-08-19", "raw": "19 August"},
    },
    "dynamic": {
        "truck_count": {"concept": "truck count", "type": "count", "value": 5},
        "kit_invoice": {"concept": "kit invoice", "type": "money",
                        "value": 850, "currency": "INR"},
        "tarpaulin_count": {"concept": "tarpaulin count", "type": "count", "value": 600},
    },
}


def test_a_query_naming_a_field_selects_it() -> None:
    result = retrieve_minimum("How many trucks do we have now?", RELIEF_STATE)
    assert result["metadata"]["subset_keys"] == ["dynamic.truck_count"]
    assert result["metadata"]["retrieval_mode"] == "field_match"


def test_plurals_match_their_field() -> None:
    """`_same_word` needs a four-character stem, so "kits"/"kit" misses and the
    answer loses the field it needed."""
    keys = retrieve_minimum("how many kits can we cover?", RELIEF_STATE)["metadata"]["subset_keys"]
    assert "dynamic.kit_invoice" in keys


def test_field_matching_widens_an_intent_match_never_narrows_it() -> None:
    """"budget" hits the intent map, which returns `constraints.*` and stops —
    leaving `dynamic.kit_invoice` behind on a question that names both."""
    keys = retrieve_minimum(
        "How many kits can we cover with the current budget?", RELIEF_STATE
    )["metadata"]["subset_keys"]
    assert "constraints.budget.max" in keys      # from the intent map
    assert "dynamic.kit_invoice" in keys         # from the field name


def test_an_unrelated_query_still_discloses_nothing() -> None:
    """The property that makes this safe to run before the size fallback:
    matching on field names must not become "disclose everything"."""
    result = retrieve_minimum("Tell me a joke", RELIEF_STATE)
    assert result["subset"] == {}
    assert result["metadata"]["retrieval_mode"] == "broad_fallback"


def test_field_matching_reads_the_leaf_not_the_section() -> None:
    """Nobody asks about "constraints"; they ask about the deadline."""
    keys = retrieve_minimum("what is the deadline again?", RELIEF_STATE)["metadata"]["subset_keys"]
    assert keys == ["constraints.deadline"]
