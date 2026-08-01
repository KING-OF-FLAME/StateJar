"""Tests for the env-gated semantic retrieval fallback.

Embeddings are mocked throughout, so these run in CI with neither torch nor
sentence-transformers installed. Every behavioural case is asserted in BOTH
modes: with the fallback off, retrieval must be byte-identical to today's
intent-map behaviour.
"""

import copy
import math
from collections.abc import Generator
from typing import Any

import pytest

from app.config import get_settings
from app.memory import retriever
from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.extractor import extract_state
from app.memory.handle import generate_handle
from app.memory.retriever import (
    MODE_BROAD,
    MODE_INTENT,
    MODE_SEMANTIC,
    SEMANTIC_THRESHOLD,
    retrieve_minimum,
)

AYAAN_STATE: dict[str, Any] = {
    "facts": {"name": "Ayaan", "city": "Pune"},
    "preferences": {"contact_mode": "email", "theme": "dark"},
    "decisions": {"choice": "blue variant"},
    "constraints": {"budget_inr_max": 2000},
    "goals": {"primary": "renovate kitchen"},
    "unresolved": [{"field": "delivery_time", "reason": "not provided"}],
    "conflicts": [],
}


class FakeEmbedder:
    """Stands in for a SentenceTransformer (no torch needed).

    The query embeds to the unit vector [1, 0]; a candidate with target
    similarity c embeds to [c, sqrt(1 - c**2)], whose cosine with the query
    is exactly c. That makes threshold and ranking assertions precise.
    """

    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores
        self.calls: list[list[str]] = []

    def encode(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        vectors = [[1.0, 0.0]]  # texts[0] is always the query
        for text in texts[1:]:
            score = self._scores.get(text.split(":", 1)[0], 0.0)
            vectors.append([score, math.sqrt(max(0.0, 1 - score * score))])
        return vectors


@pytest.fixture(autouse=True)
def _clean_env() -> Generator[None, None, None]:
    """Settings are cached and the model is a singleton — reset both."""
    get_settings.cache_clear()
    retriever._semantic_state.update(attempted=False, model=None)
    yield
    get_settings.cache_clear()
    retriever._semantic_state.update(attempted=False, model=None)


def _use_semantic(
    monkeypatch: pytest.MonkeyPatch, scores: dict[str, float]
) -> FakeEmbedder:
    """Switch the fallback on with a mocked embedding model."""
    monkeypatch.setenv("RETRIEVER_SEMANTIC", "true")
    get_settings.cache_clear()
    fake = FakeEmbedder(scores)
    monkeypatch.setattr(retriever, "_load_semantic_model", lambda: fake)
    return fake


def _intent_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVER_SEMANTIC", "false")
    get_settings.cache_clear()


# --- gating -------------------------------------------------------------------


def test_default_is_off() -> None:
    assert get_settings().retriever_semantic is False


def test_off_mode_never_loads_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The embedding model must not even be imported in production mode."""
    _intent_only(monkeypatch)
    monkeypatch.setattr(
        retriever, "_load_semantic_model",
        lambda: pytest.fail("embedding model loaded while RETRIEVER_SEMANTIC=false"),
    )
    result = retrieve_minimum("Tell me a joke", AYAAN_STATE)
    assert result["subset"] == {}
    assert result["metadata"]["retrieval_mode"] == MODE_BROAD


def test_unavailable_model_falls_back_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVER_SEMANTIC", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(retriever, "_load_semantic_model", lambda: None)  # import failed

    result = retrieve_minimum("Tell me a joke", AYAAN_STATE)
    assert result["metadata"]["retrieval_mode"] == MODE_BROAD  # degraded, not crashed
    assert result["subset"] == {}


def test_encode_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVER_SEMANTIC", "true")
    get_settings.cache_clear()

    class Exploding:
        def encode(self, texts: list[str]) -> Any:
            raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(retriever, "_load_semantic_model", lambda: Exploding())
    result = retrieve_minimum("Tell me a joke", AYAAN_STATE)
    assert result["metadata"]["retrieval_mode"] == MODE_BROAD
    assert result["subset"] == {}


def test_model_is_loaded_at_most_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed load must not be retried on every query."""
    monkeypatch.setenv("RETRIEVER_SEMANTIC", "true")
    get_settings.cache_clear()
    attempts = {"n": 0}

    import builtins

    real_import = builtins.__import__

    def _guard(name: str, *a: Any, **k: Any) -> Any:
        if name == "sentence_transformers":
            attempts["n"] += 1
            raise ImportError("No module named 'sentence_transformers'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _guard)
    for _ in range(3):
        retrieve_minimum("Tell me a joke", AYAAN_STATE)
    assert attempts["n"] == 1


# --- the fallback only ever fires on an unmatched intent ----------------------


@pytest.mark.parametrize("semantic", [False, True])
def test_matched_intent_is_identical_in_both_modes(
    semantic: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A query the intent map recognises must not consult embeddings at all."""
    if semantic:
        # every field scores 0.99 — if the layer ran, the subset would balloon
        _use_semantic(monkeypatch, {k: 0.99 for k in (
            "facts.name", "facts.city", "preferences.contact_mode",
            "preferences.theme", "decisions.choice", "constraints.budget_inr_max",
            "goals.primary",
        )})
    else:
        _intent_only(monkeypatch)

    result = retrieve_minimum("Book my delivery with my usual preferences", AYAAN_STATE)
    assert result["metadata"]["retrieval_mode"] == MODE_INTENT
    assert result["subset"] == {
        "preferences": {"contact_mode": "email"},
        "constraints": {"budget_inr_max": 2000},
        "unresolved": [{"field": "delivery_time", "reason": "not provided"}],
    }


def test_semantic_fills_an_unmatched_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """"How do I reach out about money?" hits no keyword, but means budget."""
    _use_semantic(monkeypatch, {"constraints.budget_inr_max": 0.71, "facts.city": 0.12})
    result = retrieve_minimum("What can I spend on this?", AYAAN_STATE)

    assert result["metadata"]["retrieval_mode"] == MODE_SEMANTIC
    assert result["subset"] == {"constraints": {"budget_inr_max": 2000}}
    assert result["metadata"]["subset_keys"] == ["constraints.budget_inr_max"]


def test_threshold_is_exclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strictly greater than 0.45 — a near miss must stay undisclosed."""
    _use_semantic(monkeypatch, {
        "facts.name": SEMANTIC_THRESHOLD + 0.01,   # 0.46 → in
        "facts.city": SEMANTIC_THRESHOLD,          # 0.45 → out
        "goals.primary": SEMANTIC_THRESHOLD - 0.01,  # 0.44 → out
    })
    result = retrieve_minimum("zzz unmatched query", AYAAN_STATE)
    assert result["subset"] == {"facts": {"name": "Ayaan"}}


def test_top_five_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """All seven fields clear the bar; only the five best may be disclosed."""
    _use_semantic(monkeypatch, {
        "facts.name": 0.90, "facts.city": 0.89, "preferences.contact_mode": 0.88,
        "preferences.theme": 0.87, "decisions.choice": 0.86,
        "constraints.budget_inr_max": 0.85, "goals.primary": 0.84,
    })
    result = retrieve_minimum("zzz unmatched query", AYAAN_STATE)

    assert len(result["metadata"]["subset_keys"]) == 5
    # the two weakest are dropped
    assert "constraints" not in result["subset"]
    assert "goals" not in result["subset"]
    assert set(result["metadata"]["subset_keys"]) == {
        "facts.name", "facts.city", "preferences.contact_mode",
        "preferences.theme", "decisions.choice",
    }


def test_nothing_over_threshold_reports_broad(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ran, found nothing: the mode names what actually chose the subset."""
    fake = _use_semantic(monkeypatch, {"facts.name": 0.10})
    result = retrieve_minimum("zzz unmatched query", AYAAN_STATE)

    assert fake.calls  # it really did run
    assert result["metadata"]["retrieval_mode"] == MODE_BROAD
    assert result["subset"] == {}


def test_related_unresolved_rides_along(monkeypatch: pytest.MonkeyPatch) -> None:
    """Semantic hits pull in their unresolved entries, as intent mode does."""
    state = copy.deepcopy(AYAAN_STATE)
    state["unresolved"] = [{"field": "theme", "reason": "user unsure"}]
    _use_semantic(monkeypatch, {"preferences.theme": 0.80})

    result = retrieve_minimum("zzz unmatched query", state)
    assert result["subset"] == {
        "preferences": {"theme": "dark"},
        "unresolved": [{"field": "theme", "reason": "user unsure"}],
    }


def test_embedded_text_is_path_plus_value(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _use_semantic(monkeypatch, {})
    retrieve_minimum("zzz unmatched query", AYAAN_STATE)

    sent = fake.calls[0]
    assert sent[0] == "zzz unmatched query"
    assert "facts.name: Ayaan" in sent
    assert "constraints.budget_inr_max: 2000" in sent
    # list sections are not embedded; they ride along via relatedness
    assert not any(s.startswith("unresolved") for s in sent)


# --- CRITICAL: the write path is untouched (patent guarantee) ------------------


@pytest.mark.parametrize("query", [
    "Book my delivery",        # intent_map
    "What can I spend here?",  # semantic_fallback
    "Tell me a joke",          # broad_fallback
])
def test_handle_is_byte_identical_with_semantic_on_and_off(
    query: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retrieval is a read path: no mode of it may change the stored identity.

    Runs the real write path (extract → canonicalize → handle) on both sides
    with a retrieval in between, and compares the canonical bytes, not just
    the handle string.
    """
    text = "My name is Ayaan from Pune, budget under ₹2000. I prefer email."

    _intent_only(monkeypatch)
    state_off = extract_state(text).model_dump()
    canonical_off = canonicalize(state_off)
    retrieve_minimum(query, state_off)
    handle_off = generate_handle(canonical_off, SCHEMA_VERSION, NORM_VERSION)

    _use_semantic(monkeypatch, {
        "facts.name": 0.91, "constraints.budget_inr_max": 0.88,
        "preferences.contact_mode": 0.77,
    })
    state_on = extract_state(text).model_dump()
    canonical_on = canonicalize(state_on)
    retrieve_minimum(query, state_on)
    handle_on = generate_handle(canonical_on, SCHEMA_VERSION, NORM_VERSION)

    assert canonical_off == canonical_on          # byte-identical
    assert handle_off == handle_on
    assert "retrieval_mode" not in canonical_off  # metadata is never serialized


@pytest.mark.parametrize("semantic", [False, True])
def test_retrieval_never_mutates_the_state(
    semantic: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If retrieval could edit the state in place, the next handle would drift."""
    if semantic:
        _use_semantic(monkeypatch, {"facts.name": 0.9, "preferences.theme": 0.8})
    else:
        _intent_only(monkeypatch)

    state = copy.deepcopy(AYAAN_STATE)
    before = canonicalize(copy.deepcopy(state))
    for query in ("Book my delivery", "What can I spend here?", "Tell me a joke"):
        retrieve_minimum(query, state)
    assert canonicalize(state) == before
    assert state == AYAAN_STATE
