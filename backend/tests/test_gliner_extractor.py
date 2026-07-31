"""Tests for the env-gated GLiNER extraction layer.

GLiNER is mocked throughout, so these run in CI with neither torch nor the
gliner package installed. Every messy-input case is asserted in BOTH modes:
rules-mode output must be byte-identical to today's behaviour, and gliner
may only ever add fields the rules left empty.
"""

from collections.abc import Generator
from typing import Any

import pytest

from app.config import get_settings
from app.memory import extractor
from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.extractor import (
    SOURCE_GLINER,
    SOURCE_RULES,
    extract_state,
    extract_state_with_source,
)
from app.memory.handle import generate_handle


class FakeGliner:
    """Stands in for a loaded GLiNER model (no torch needed)."""

    def __init__(self, entities: list[dict[str, Any]]) -> None:
        self._entities = entities
        self.calls: list[str] = []

    def predict_entities(self, text: str, labels: list[str]) -> list[dict[str, Any]]:
        self.calls.append(text)
        return self._entities


@pytest.fixture(autouse=True)
def _clean_env() -> Generator[None, None, None]:
    """Settings are cached and the model is a singleton — reset both."""
    get_settings.cache_clear()
    extractor._gliner_state.update(attempted=False, model=None)
    yield
    get_settings.cache_clear()
    extractor._gliner_state.update(attempted=False, model=None)


def _use_gliner(monkeypatch: pytest.MonkeyPatch, entities: list[dict[str, Any]]) -> FakeGliner:
    """Switch to gliner mode with a mocked model."""
    monkeypatch.setenv("EXTRACTOR_MODE", "gliner")
    get_settings.cache_clear()
    fake = FakeGliner(entities)
    monkeypatch.setattr(extractor, "_load_gliner_model", lambda: fake)
    return fake


def _rules_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTOR_MODE", "rules")
    get_settings.cache_clear()


# --- gating -------------------------------------------------------------------


def test_default_mode_is_rules() -> None:
    assert get_settings().extractor_mode == "rules"
    _, source = extract_state_with_source("My name is Ayaan")
    assert source == SOURCE_RULES


def test_rules_mode_never_touches_gliner(monkeypatch: pytest.MonkeyPatch) -> None:
    """The neural layer must not even be imported in production mode."""
    _rules_only(monkeypatch)
    called = False

    def _boom() -> Any:
        nonlocal called
        called = True
        raise AssertionError("gliner must not be loaded in rules mode")

    monkeypatch.setattr(extractor, "_load_gliner_model", _boom)
    state, source = extract_state_with_source("My name is Ayaan, budget under ₹2000")
    assert source == SOURCE_RULES
    assert called is False
    assert state.facts["name"] == "Ayaan"


def test_unavailable_gliner_falls_back_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTOR_MODE", "gliner")
    get_settings.cache_clear()
    monkeypatch.setattr(extractor, "_load_gliner_model", lambda: None)  # import failed

    state, source = extract_state_with_source("My name is Ayaan, budget under ₹2000")
    assert source == SOURCE_RULES              # degraded, not crashed
    assert state.facts["name"] == "Ayaan"      # rules still ran


def test_gliner_prediction_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTOR_MODE", "gliner")
    get_settings.cache_clear()

    class Exploding:
        def predict_entities(self, text: str, labels: list[str]) -> Any:
            raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(extractor, "_load_gliner_model", lambda: Exploding())
    state, source = extract_state_with_source("My name is Ayaan")
    assert source == SOURCE_RULES
    assert state.facts["name"] == "Ayaan"


def test_model_is_loaded_at_most_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed load must not be retried on every message."""
    monkeypatch.setenv("EXTRACTOR_MODE", "gliner")
    get_settings.cache_clear()
    attempts = {"n": 0}

    def _fail_import(*_a: Any, **_k: Any) -> Any:
        attempts["n"] += 1
        raise ImportError("No module named 'gliner'")

    monkeypatch.setattr(extractor, "GLINER_MODEL_NAME", "x")
    monkeypatch.setitem(extractor._gliner_state, "attempted", False)
    import builtins

    real_import = builtins.__import__

    def _guard(name: str, *a: Any, **k: Any) -> Any:
        if name == "gliner":
            return _fail_import()
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _guard)
    for _ in range(3):
        extract_state_with_source("My name is Ayaan")
    assert attempts["n"] == 1


# --- rules always win ---------------------------------------------------------


def test_gliner_never_overwrites_a_rule_value(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "My name is Ayaan, budget under ₹2000. I prefer email."
    rules_state = extract_state(text)

    _use_gliner(monkeypatch, [
        {"label": "person name", "text": "Rohan"},          # conflicts with Ayaan
        {"label": "money amount", "text": "99,999"},        # conflicts with 2000
        {"label": "contact preference", "text": "call me"},  # conflicts with email
        {"label": "decision", "text": "express shipping"},   # a genuine gap
    ])
    merged, source = extract_state_with_source(text)

    assert source == SOURCE_GLINER
    assert merged.facts["name"] == "Ayaan"                    # rule wins
    assert merged.constraints["budget_inr_max"] == 2000       # rule wins
    assert "budget_inr" not in merged.constraints             # no fabricated 2nd key
    assert merged.preferences["contact_mode"] == "email"      # rule wins
    assert merged.decisions["choice"] == "express shipping"   # gap filled
    # everything the rules produced is still present, untouched
    assert rules_state.facts == merged.facts


# --- messy real-world inputs, asserted in BOTH modes ---------------------------

MESSY_CASES = [
    pytest.param(
        "mera naam Rohan hai Delhi se, budget 40k tak",
        [{"label": "person name", "text": "Rohan"}, {"label": "money amount", "text": "40k"}],
        {"facts": {"name": "Rohan"}, "constraints": {"budget_inr": 40000}},
        id="hinglish-name-and-40k",
    ),
    pytest.param(
        "budget 2000 se zyada nahi hona chahiye",
        [{"label": "money amount", "text": "2000"}],
        {"constraints": {"budget_inr": 2000}},
        id="hinglish-budget-ceiling",
    ),
    pytest.param(
        "Hi, I'm Aarav Sharma from Pune. I prefer WhatsApp only, never call me. "
        "At least 16GB RAM.",
        [{"label": "person name", "text": "Aarav Sharma"}],
        {"facts": {"name": "Aarav Sharma"}},
        id="english-name-and-whatsapp",
    ),
    pytest.param(
        "Ship it by Friday, and the review call is on 12 March.",
        [
            {"label": "date or deadline", "text": "Friday"},
            {"label": "date or deadline", "text": "12 March"},
        ],
        {},  # rules already catch "by Friday"; gliner must not overwrite it
        id="two-dates",
    ),
    pytest.param(
        "I'll go with the annual plan, but I haven't decided the start date.",
        [{"label": "decision", "text": "monthly plan"}],
        {},  # rules found the decision; gliner's competing one must lose
        id="decision-plus-unresolved",
    ),
]


@pytest.mark.parametrize("text,entities,gliner_adds", MESSY_CASES)
def test_messy_input_rules_mode_unchanged(
    text: str, entities: list[dict[str, Any]], gliner_adds: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rules mode must behave exactly as before — gliner is never consulted."""
    _rules_only(monkeypatch)
    monkeypatch.setattr(
        extractor, "_load_gliner_model",
        lambda: pytest.fail("gliner consulted in rules mode"),
    )
    state, source = extract_state_with_source(text)
    assert source == SOURCE_RULES
    # the untouched rule engine is the reference implementation
    assert state.model_dump() == extractor._extract_rules(text).model_dump()


@pytest.mark.parametrize("text,entities,gliner_adds", MESSY_CASES)
def test_messy_input_gliner_mode_only_adds(
    text: str, entities: list[dict[str, Any]], gliner_adds: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gliner mode keeps every rule value and may only fill empty fields."""
    rules_state = extractor._extract_rules(text).model_dump()

    fake = _use_gliner(monkeypatch, entities)
    merged, source = extract_state_with_source(text)
    assert source == SOURCE_GLINER
    assert fake.calls == [text]

    merged_dump = merged.model_dump()
    for section, rule_values in rules_state.items():
        if isinstance(rule_values, dict):
            for key, value in rule_values.items():
                assert merged_dump[section][key] == value, (
                    f"gliner overwrote rule value {section}.{key}"
                )
        else:  # unresolved / conflicts lists are rule-owned
            assert merged_dump[section] == rule_values

    for section, expected in gliner_adds.items():
        for key, value in expected.items():
            assert merged_dump[section][key] == value


# --- identity is unaffected by the extraction source --------------------------


def test_handle_is_identical_regardless_of_extraction_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extraction_source is metadata: it must never reach the canonical bytes."""
    text = "My name is Ayaan, budget under ₹2000. I prefer email."

    _rules_only(monkeypatch)
    rules_state, rules_source = extract_state_with_source(text)

    # gliner runs but predicts only what the rules already found, so the
    # extracted state is identical and only the source label differs
    _use_gliner(monkeypatch, [
        {"label": "person name", "text": "Ayaan"},
        {"label": "contact preference", "text": "email"},
    ])
    gliner_state, gliner_source = extract_state_with_source(text)

    assert rules_source == SOURCE_RULES and gliner_source == SOURCE_GLINER
    assert rules_state.model_dump() == gliner_state.model_dump()

    canonical_rules = canonicalize(rules_state.model_dump())
    canonical_gliner = canonicalize(gliner_state.model_dump())
    assert canonical_rules == canonical_gliner              # byte-identical
    assert "extraction_source" not in canonical_rules       # never serialized

    assert generate_handle(canonical_rules, SCHEMA_VERSION, NORM_VERSION) == generate_handle(
        canonical_gliner, SCHEMA_VERSION, NORM_VERSION
    )


def test_money_parsing() -> None:
    assert extractor._parse_money("40k") == 40000
    assert extractor._parse_money("₹2,000") == 2000
    assert extractor._parse_money("1.5 lakh") == 150000
    assert extractor._parse_money("no digits here") is None
