"""Hard extraction cases — the messy input real users actually type.

GLiNER2 and the LLM tier are mocked throughout, so this runs in CI with
neither torch nor a network. Every case asserts exact field paths and values,
because "it extracted something" is how the original engine passed while
naming people "via".
"""

from __future__ import annotations

import json
import re
from collections.abc import Generator
from typing import Any

import pytest

from app.config import get_settings
from app.memory import extractor
from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.extractor import (
    SOURCE_GLINER,
    SOURCE_LLM,
    SOURCE_RULES,
    StructuredState,
    extract,
    extract_rules,
)
from app.memory.handle import generate_handle
from app.schema import canonical as canon


@pytest.fixture(autouse=True)
def _rules_only(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Tier 1 alone unless a test opts in — results must not depend on
    whether the optional ML extras happen to be installed."""
    monkeypatch.setenv("EXTRACTOR_MODE", "rules")
    monkeypatch.setenv("EXTRACTOR_LLM_FALLBACK", "false")
    get_settings.cache_clear()
    extractor._gliner_state.update(attempted=False, model=None)
    yield
    get_settings.cache_clear()
    extractor._gliner_state.update(attempted=False, model=None)


def fields(state: StructuredState) -> dict[str, Any]:
    """Flat canonical-path view, so assertions read like the registry.

    Paths are nested now (`constraints.budget.max`), and money and dates are
    normalized objects. Those objects are unwrapped to the primitive they
    carry — the tests are about which field got which amount, not about the
    shape of the envelope, which `test_normalizers.py` covers directly.
    """
    out: dict[str, Any] = {}
    dumped = state.model_dump()
    for section in canon.ACTIVE_SECTIONS:
        for path in canon.leaf_paths_in(dumped.get(section), section):
            value = canon.read_path(dumped, path)
            if isinstance(value, dict):
                value = value.get("value", value.get("iso", value))
            out[path] = value
    for item in dumped.get("unresolved") or []:
        out[f"unresolved.{item['field']}"] = item["reason"]
    return out


# --- 1. the sentence that was broken in production ----------------------------


def test_the_failing_production_sentence() -> None:
    """Previously yielded one field, and once named the user "via"."""
    got = fields(extract("hi i am yashraj , i am from pune, i have 3000rs rupee , "
                         "i prefer email").state)
    assert got == {
        "facts.name": "Yashraj",
        "facts.city": "Pune",
        "constraints.budget.max": 3000,
        "preferences.contact_mode": "email",
    }
    assert len(got) == 4


def test_filler_words_are_never_names() -> None:
    """The exact regression: `[A-Z]` under IGNORECASE matched "via"."""
    result = extract("can you call me via call instead of email")
    got = fields(result.state)
    assert got["preferences.contact_mode"] == "phone"
    assert "facts.name" not in got
    conflicts = result.state.model_dump()["conflicts"]
    assert conflicts and conflicts[0]["field"] == "contact_mode"
    assert set(conflicts[0]["values"]) == {"phone", "email"}


@pytest.mark.parametrize("text", [
    "i am from pune",
    "call me via whatsapp",
    "i am here",
    "hi hello",
    "i'm just looking",
    "this is the thing",
])
def test_stopwords_never_become_a_name(text: str) -> None:
    assert "facts.name" not in fields(extract(text).state)


# --- 2. multi-clause English --------------------------------------------------


def test_long_english_multi_clause() -> None:
    got = fields(extract(
        "hi i'm Aarav Sharma from Pune, budget 40k, prefer whatsapp only, "
        "never call me, at least 16GB RAM"
    ).state)
    assert got["facts.name"] == "Aarav Sharma"
    assert got["facts.city"] == "Pune"
    assert got["constraints.budget.max"] == 40000
    assert got["preferences.contact_mode"] == "whatsapp"
    assert got["constraints.requirements"] == ["16GB RAM"]


def test_every_clause_contributes() -> None:
    """The old engine stopped at the first match."""
    got = fields(extract(
        "my name is Neha, i am from Bengaluru, budget under 25000, i prefer sms"
    ).state)
    assert got["facts.name"] == "Neha"
    assert got["facts.city"] == "Bengaluru"
    assert got["constraints.budget.max"] == 25000   # "under" is a ceiling
    assert got["preferences.contact_mode"] == "sms"


# --- 3. Hinglish ---------------------------------------------------------------


def test_hinglish_name_city_and_ceiling() -> None:
    got = fields(extract(
        "mera naam Rohan hai Delhi se, budget 2000 se zyada nahi hona chahiye"
    ).state)
    assert got["facts.name"] == "Rohan"
    assert got["facts.city"] == "Delhi"
    assert got["constraints.budget.max"] == 2000


def test_hinglish_decision_and_unresolved() -> None:
    got = fields(extract(
        "main Priya hoon, 1.5 lakh tak ka budget, decision final hai — ASUS lunga, "
        "delivery date abhi decide nahi kiya"
    ).state)
    assert got["facts.name"] == "Priya"
    assert got["constraints.budget.max"] == 150000     # "tak" is a ceiling
    assert got["decisions.choice"] == "ASUS"               # not the particle "hai"
    assert "unresolved.delivery_date" in got


# --- 4. money forms ------------------------------------------------------------


@pytest.mark.parametrize("text,path,value", [
    ("i have 3000rs", "constraints.budget.max", 3000),
    ("i have 3000 rs", "constraints.budget.max", 3000),
    ("rs 3000 is my budget", "constraints.budget.max", 3000),
    ("₹3000 available", "constraints.budget.max", 3000),
    ("3000 rupees in hand", "constraints.budget.max", 3000),
    ("my budget is 3k", "constraints.budget.max", 3000),
    ("budget 40k", "constraints.budget.max", 40000),
    ("1.5 lakh ka budget", "constraints.budget.max", 150000),
    ("2 crore budget", "constraints.budget.max", 20000000),
    ("budget under 2000", "constraints.budget.max", 2000),
    ("max 5k", "constraints.budget.max", 5000),
    ("40k tak", "constraints.budget.max", 40000),
    ("2000 rupees se zyada nahi", "constraints.budget.max", 2000),
    ("not more than 1 lakh", "constraints.budget.max", 100000),
])
def test_money_forms(text: str, path: str, value: int) -> None:
    assert fields(extract(text).state).get(path) == value


@pytest.mark.parametrize("text", [
    "2000 se zyada nahi",          # a ceiling on an unnamed quantity
    "nothing over 4999",
    "max 24",
])
def test_a_bare_ceiling_is_not_money(text: str) -> None:
    """A qualifier says how much, never of what.

    These used to become rupees because a ceiling word alone made any nearby
    number an amount — the same path that stored "24 tonnes" as ₹24.
    """
    assert "constraints.budget.max" not in fields(extract(text).state)


def test_specs_are_not_mistaken_for_money() -> None:
    """"16GB" and "3 sessions" are numbers, not budgets."""
    got = fields(extract("i need at least 16GB RAM and 3 sessions").state)
    assert "constraints.budget.max" not in got


# --- 5. contact synonyms -------------------------------------------------------


@pytest.mark.parametrize("text,mode", [
    ("i prefer email", "email"),
    ("prefer mail", "email"),
    ("please contact me by phone", "phone"),
    ("prefer voice", "phone"),
    ("reach me on whatsapp", "whatsapp"),
    ("prefer wa", "whatsapp"),
    ("contact me by sms", "sms"),
])
def test_contact_synonyms(text: str, mode: str) -> None:
    assert fields(extract(text).state).get("preferences.contact_mode") == mode


# --- 6. dates, goals, greetings, noise ----------------------------------------


def test_two_dates_in_one_sentence() -> None:
    got = fields(extract(
        "ship it by Friday and the review call is on 12 March"
    ).state)
    # both are normalized to ISO now. "Friday" resolves against today, so the
    # assertion is on the shape; the second date is checked on month and day,
    # which is the part the sentence actually fixes.
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", got["constraints.deadline"])
    assert [d[5:] for d in got["constraints.additional_dates"]] == ["03-12"]


def test_iso_date_survives_intact() -> None:
    assert fields(extract("deadline is 2026-08-15").state)["constraints.deadline"] == "2026-08-15"


def test_decision_plus_unresolved() -> None:
    got = fields(extract(
        "i'll go with the annual plan, but i haven't decided the start date"
    ).state)
    assert got["decisions.choice"] == "annual plan"
    assert got["unresolved.start_date"] == "not provided"


def test_plain_greeting_extracts_nothing() -> None:
    for greeting in ("hello there", "hi!", "hey, good morning", "thanks!"):
        assert fields(extract(greeting).state) == {}, greeting


def test_emoji_heavy_message() -> None:
    got = fields(extract(
        "🎉 hey!! i'm Meera 🇮🇳 from Jaipur, budget ~2.5 lakh 💸, whatsapp only pls 🙏"
    ).state)
    assert got["facts.name"] == "Meera"
    assert got["facts.city"] == "Jaipur"
    assert got["constraints.budget.max"] == 250000
    assert got["preferences.contact_mode"] == "whatsapp"


def test_long_rambling_paragraph() -> None:
    got = fields(extract(
        "so anyway i was thinking about this for a while and honestly it took me "
        "ages to decide but my name is Kabir and i am from Hyderabad, the budget "
        "i can manage is around 75000 rupees give or take, and honestly i would "
        "much prefer email because calls are hard for me during work hours, "
        "also i haven't decided the delivery window yet"
    ).state)
    assert got["facts.name"] == "Kabir"
    assert got["facts.city"] == "Hyderabad"
    assert got["constraints.budget.max"] == 75000
    assert got["preferences.contact_mode"] == "email"
    assert "unresolved.delivery_window" in got


# --- 7. tier plumbing ----------------------------------------------------------


class FakeGliner:
    def __init__(self, entities: list[dict[str, Any]]) -> None:
        self._entities = entities
        self.calls: list[str] = []

    def predict_entities(self, text: str, labels: list[str]) -> list[dict[str, Any]]:
        self.calls.append(text)
        return self._entities


def _use_gliner(monkeypatch: pytest.MonkeyPatch, entities: list[dict[str, Any]]) -> FakeGliner:
    monkeypatch.setenv("EXTRACTOR_MODE", "gliner")
    get_settings.cache_clear()
    fake = FakeGliner(entities)
    monkeypatch.setattr(extractor, "_load_gliner_model", lambda: fake)
    return fake


def test_gliner_fills_only_what_rules_missed(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "my name is Ayaan, i prefer email"
    _use_gliner(monkeypatch, [
        {"label": "person name", "text": "Rohan", "score": 0.99},   # conflicts
        {"label": "city", "text": "Mumbai", "score": 0.95},         # a real gap
    ])
    result = extract(text)
    got = fields(result.state)

    assert got["facts.name"] == "Ayaan"      # rules win
    assert got["facts.city"] == "Mumbai"     # gap filled
    assert result.sources == [SOURCE_RULES, SOURCE_GLINER]
    assert result.origins["facts.name"] == SOURCE_RULES
    assert result.origins["facts.city"] == SOURCE_GLINER


def test_gliner_spans_obey_the_same_stopwords(monkeypatch: pytest.MonkeyPatch) -> None:
    """A neural span is no more entitled to name someone "via" than a regex."""
    _use_gliner(monkeypatch, [{"label": "person name", "text": "via", "score": 0.99}])
    assert "facts.name" not in fields(extract("call me via call").state)


def test_low_confidence_spans_are_discarded(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_gliner(monkeypatch, [{"label": "city", "text": "Mumbai", "score": 0.2}])
    assert "facts.city" not in fields(extract("some vague sentence here").state)


def test_missing_gliner_degrades_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTOR_MODE", "gliner")
    get_settings.cache_clear()
    monkeypatch.setattr(extractor, "_load_gliner_model", lambda: None)
    result = extract("my name is Ayaan")
    assert result.sources == [SOURCE_RULES]
    assert fields(result.state)["facts.name"] == "Ayaan"


def test_llm_tier_only_fires_on_long_thin_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTOR_LLM_FALLBACK", "true")
    get_settings.cache_clear()
    short = extractor.extract_rules("my name is Ayaan")[0]
    assert extractor._llm_should_run("my name is Ayaan", short) is False

    rambling = ("so i was wondering whether the thing we discussed the other day "
                "is still something you would be able to help me out with at all")
    thin, _ = extractor.extract_rules(rambling)
    assert extractor._llm_should_run(rambling, thin) is True


def test_llm_tier_fills_gaps_and_is_labelled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTOR_LLM_FALLBACK", "true")
    get_settings.cache_clear()
    rambling = ("so i was wondering whether the thing we discussed the other day "
                "is still something you could help with, the person to reach is "
                "someone in our team over in that city we mentioned")
    monkeypatch.setattr(
        extractor, "merge_llm",
        lambda text, state, origins, db=None, user_id=None: (
            state.facts.__setitem__("city", "Chennai"),
            origins.__setitem__("facts.city", SOURCE_LLM),
            True,
        )[-1],
    )
    result = extract(rambling, db=object(), user_id=1)
    assert result.sources == [SOURCE_RULES, SOURCE_LLM]
    assert result.origins["facts.city"] == SOURCE_LLM


def test_llm_tier_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """No key, no credit, malformed JSON — all must be survivable."""
    monkeypatch.setenv("EXTRACTOR_LLM_FALLBACK", "true")
    get_settings.cache_clear()

    def explode(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("no provider key saved")

    monkeypatch.setattr("app.llm.gateway.chat", explode, raising=False)
    state, origins = extract_rules("hello")
    assert extractor.merge_llm("hello", state, origins, db=object(), user_id=1) is False


@pytest.mark.parametrize("reply", [
    "not json at all",
    "{broken",
    '{"facts": "not a dict"}',
    "",
])
def test_llm_bad_payloads_are_ignored(reply: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.gateway.chat",
                        lambda *a, **k: {"text": reply}, raising=False)
    state, origins = extract_rules("hello")
    extractor.merge_llm("hello", state, origins, db=object(), user_id=1)
    assert fields(state) == {}


# --- 8. identity is unaffected by which tier answered -------------------------


def test_handle_is_identical_regardless_of_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    """The architectural claim: extraction happens before canonicalization, so
    a probabilistic tier can change *what* is known but never how it hashes."""
    text = "my name is Ayaan, i prefer email"

    rules_state, _ = extract_rules(text)

    # gliner runs but proposes only what the rules already found, so the
    # extracted fields are identical and only the label differs
    _use_gliner(monkeypatch, [
        {"label": "person name", "text": "Ayaan", "score": 0.99},
        {"label": "contact preference", "text": "email", "score": 0.99},
    ])
    tiered = extract(text)

    assert tiered.sources == [SOURCE_RULES, SOURCE_GLINER]
    assert rules_state.model_dump() == tiered.state.model_dump()

    canonical_rules = canonicalize(rules_state.model_dump())
    canonical_tiered = canonicalize(tiered.state.model_dump())
    assert canonical_rules == canonical_tiered              # byte-identical
    assert generate_handle(canonical_rules, SCHEMA_VERSION, NORM_VERSION) == \
        generate_handle(canonical_tiered, SCHEMA_VERSION, NORM_VERSION)


def test_tier_metadata_never_reaches_the_canonical_bytes() -> None:
    result = extract("my name is Ayaan, budget 2000")
    canonical = canonicalize(result.state.model_dump())
    for marker in ("extraction_source", "origins", SOURCE_RULES, SOURCE_GLINER, SOURCE_LLM):
        assert marker not in canonical
    # the metadata does exist — it is just carried outside `state`
    assert result.sources == [SOURCE_RULES]
    assert result.origins["facts.name"] == SOURCE_RULES


def test_origins_cover_every_extracted_field() -> None:
    """The UI shows a per-field origin, so every field must have one."""
    result = extract("hi i am yashraj , i am from pune, i have 3000rs rupee , "
                     "i prefer email")
    for path in fields(result.state):
        assert path in result.origins, path
        assert result.origins[path] == SOURCE_RULES


def test_extraction_is_deterministic_across_runs() -> None:
    text = "hi i'm Aarav Sharma from Pune, budget 40k, prefer whatsapp only"
    handles = {
        generate_handle(canonicalize(extract(text).state.model_dump()),
                        SCHEMA_VERSION, NORM_VERSION)
        for _ in range(20)
    }
    assert len(handles) == 1


def test_rules_mode_output_is_json_serialisable() -> None:
    """The state goes straight into a JSON column."""
    state = extract("my name is Ayaan, budget under 2000, i prefer email").state
    assert json.loads(json.dumps(state.model_dump()))
