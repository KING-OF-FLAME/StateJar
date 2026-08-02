"""Tier-2 plumbing: gating, loading, and the merge contract.

Behavioural extraction cases live in test_extractor_hard.py; this file covers
how the GLiNER2 tier is switched on, loaded and merged — the parts that must
hold even on a machine with no ML extras installed.
"""

from collections.abc import Generator
from typing import Any

import pytest

from app.config import Settings, get_settings
from app.memory import extractor
from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.extractor import (
    GLINER_SCHEMA,
    SOURCE_GLINER,
    SOURCE_RULES,
    extract,
    extract_rules,
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
    monkeypatch.setenv("EXTRACTOR_MODE", "gliner")
    get_settings.cache_clear()
    fake = FakeGliner(entities)
    monkeypatch.setattr(extractor, "_load_gliner_model", lambda: fake)
    return fake


def _rules_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTOR_MODE", "rules")
    get_settings.cache_clear()


# --- gating -------------------------------------------------------------------


def test_default_mode_is_auto() -> None:
    """The neural tier is part of the pipeline, not an opt-in.

    Asserted against the field default rather than get_settings(), because
    conftest pins the suite to rules so results never depend on whether the
    ML extras happen to be installed locally.
    """
    assert Settings.model_fields["extractor_mode"].default == extractor.MODE_AUTO


@pytest.mark.parametrize("mode,enabled", [
    ("auto", True), ("AUTO", True), ("  auto  ", True),
    ("gliner", True), ("GLiNER", True),
    ("rules", False), ("RULES", False),
    # a typo must never silently put a neural model on the write path
    ("rulez", False), ("off", False), ("", False),
])
def test_mode_parsing(mode: str, enabled: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTOR_MODE", mode)
    get_settings.cache_clear()
    assert extractor._gliner_enabled() is enabled


def test_rules_mode_never_touches_gliner(monkeypatch: pytest.MonkeyPatch) -> None:
    """The neural tier must not even be imported in production mode."""
    _rules_only(monkeypatch)
    monkeypatch.setattr(
        extractor, "_load_gliner_model",
        lambda: pytest.fail("gliner loaded while EXTRACTOR_MODE=rules"),
    )
    result = extract("My name is Ayaan, budget under 2000")
    assert result.sources == [SOURCE_RULES]
    assert result.state.facts["name"] == "Ayaan"


def test_auto_mode_runs_the_neural_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTOR_MODE", "auto")
    get_settings.cache_clear()
    monkeypatch.setattr(
        extractor, "_load_gliner_model",
        lambda: FakeGliner([{"label": "city", "text": "Pune", "score": 0.9}]),
    )
    result = extract("working out of somewhere new")
    assert result.sources == [SOURCE_RULES, SOURCE_GLINER]
    assert result.state.facts["city"] == "Pune"


def test_auto_mode_degrades_when_the_package_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What production does: default mode, no extras installed."""
    monkeypatch.setenv("EXTRACTOR_MODE", "auto")
    get_settings.cache_clear()
    monkeypatch.setattr(extractor, "_load_gliner_model", lambda: None)

    result = extract("My name is Ayaan")
    assert result.sources == [SOURCE_RULES]
    assert result.state.facts["name"] == "Ayaan"


def test_prediction_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTOR_MODE", "gliner")
    get_settings.cache_clear()

    class Exploding:
        def predict_entities(self, text: str, labels: list[str]) -> Any:
            raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(extractor, "_load_gliner_model", lambda: Exploding())
    result = extract("My name is Ayaan")
    assert result.sources == [SOURCE_RULES]
    assert result.state.facts["name"] == "Ayaan"


def test_model_is_loaded_at_most_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed load must not be retried on every message."""
    monkeypatch.setenv("EXTRACTOR_MODE", "gliner")
    get_settings.cache_clear()
    attempts = {"n": 0}

    import builtins

    real_import = builtins.__import__

    def _guard(name: str, *a: Any, **k: Any) -> Any:
        if name == "gliner":
            attempts["n"] += 1
            raise ImportError("No module named 'gliner'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _guard)
    for _ in range(3):
        extract("My name is Ayaan")
    assert attempts["n"] == 1


# --- merge contract -----------------------------------------------------------


def test_gliner_never_overwrites_a_rule_value(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "My name is Ayaan, budget under 2000, I prefer email"
    rules_state, _ = extract_rules(text)

    _use_gliner(monkeypatch, [
        {"label": "person name", "text": "Rohan", "score": 0.99},           # conflicts
        {"label": "monetary amount", "text": "99,999", "score": 0.99},      # conflicts
        {"label": "contact preference", "text": "call", "score": 0.99},     # conflicts
        {"label": "decision", "text": "express shipping", "score": 0.99},   # a real gap
    ])
    result = extract(text)

    assert result.sources == [SOURCE_RULES, SOURCE_GLINER]
    assert result.state.facts["name"] == "Ayaan"                  # rule wins
    assert result.state.constraints["budget_inr_max"] == 2000     # rule wins
    assert "budget_inr" not in result.state.constraints           # no second key
    assert result.state.preferences["contact_mode"] == "email"    # rule wins
    assert result.state.decisions["choice"] == "express shipping"  # gap filled
    assert result.state.facts == rules_state.facts


def test_every_schema_label_has_a_destination() -> None:
    """A label the model is prompted with but nothing maps is a silent drop."""
    for label, target in GLINER_SCHEMA.items():
        assert isinstance(target, tuple) and len(target) == 2, label
        section, key = target
        assert section in ("facts", "preferences", "decisions", "constraints",
                           "goals", "unresolved"), label
        assert key


def test_back_compat_shim_returns_a_list() -> None:
    """extract_state_with_source used to return a single string."""
    state, sources = extract_state_with_source("My name is Ayaan")
    assert sources == [SOURCE_RULES]
    assert state.facts["name"] == "Ayaan"
    assert extract_state("My name is Ayaan").facts["name"] == "Ayaan"


def test_handle_is_identical_regardless_of_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier labels are metadata: they must never reach the canonical bytes."""
    text = "My name is Ayaan, budget under 2000. I prefer email."

    _rules_only(monkeypatch)
    rules_state = extract(text).state

    _use_gliner(monkeypatch, [
        {"label": "person name", "text": "Ayaan", "score": 0.99},
        {"label": "contact preference", "text": "email", "score": 0.99},
    ])
    tiered = extract(text)

    assert tiered.sources == [SOURCE_RULES, SOURCE_GLINER]
    assert rules_state.model_dump() == tiered.state.model_dump()

    canonical_rules = canonicalize(rules_state.model_dump())
    canonical_tiered = canonicalize(tiered.state.model_dump())
    assert canonical_rules == canonical_tiered
    assert SOURCE_GLINER not in canonical_rules
    assert generate_handle(canonical_rules, SCHEMA_VERSION, NORM_VERSION) == generate_handle(
        canonical_tiered, SCHEMA_VERSION, NORM_VERSION
    )
