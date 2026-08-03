"""The canonical layer: registry, normalizers, and the invariants they buy.

One test per reported bug, each written so it fails against the old behaviour
rather than merely describing the new one.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from app.memory.conflict import compare, detect_conflicts
from app.memory.extractor import extract_state
from app.memory.storage import MemoryStore
from app.memory.versioning import evolve_state, initial_state
from app.schema import canonical as canon
from app.schema import normalizers as norm

NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _ingest(text: str, state=None, handle=None):
    extracted = extract_state(text).model_dump()
    if state is None:
        return initial_state(extracted)
    return evolve_state(state, extracted, handle)


# --- BUG-1: one concept, one key ----------------------------------------------


def test_budget_aliases_all_collapse_to_one_path() -> None:
    """The root cause: six spellings that used to be six independent keys."""
    for alias in ("budget", "budget_inr", "budget_inr_max", "max_budget",
                  "price_limit", "budget_max"):
        assert canon.canonicalize(alias, "75000") == (
            "constraints.budget.max", {"value": 75000, "currency": "INR"}
        ), alias


def test_budget_update_leaves_exactly_one_value() -> None:
    """75,000 then 90,000: the stale figure must not survive anywhere live."""
    state, handle = _ingest("My budget is under 75000 rupees")
    state, handle = _ingest("Update: budget is now 90000 rupees", state, handle)

    assert state["constraints"] == {
        "budget": {"max": {"value": 90000, "currency": "INR"}}
    }
    # and nothing anywhere in active state still says 75000
    live = {k: v for k, v in state.items() if k in canon.ACTIVE_SECTIONS}
    assert "75000" not in json.dumps(live)

    # the superseded value is not lost — it moved to history
    assert [h["value"]["value"] for h in state["history"]] == [75000]


def test_superseded_value_is_not_disclosed() -> None:
    """History is an audit artifact; retrieval must never ship it."""
    from app.memory.retriever import retrieve_minimum

    state, handle = _ingest("My budget is under 75000 rupees")
    state, _ = _ingest("Update: budget is now 90000 rupees", state, handle)

    result = retrieve_minimum("what is my budget?", state)
    assert "75000" not in json.dumps(result["subset"])
    assert "history" not in result["subset"]


# --- BUG-2: no dangling fragments ---------------------------------------------


def test_pronoun_fragment_never_becomes_a_requirement() -> None:
    """"I need it before 15 August" produced requirements=["it before 15 August"]."""
    state = extract_state("I need it before 15 August").model_dump()
    assert "requirements" not in state["constraints"]
    assert state["constraints"]["deadline"]["iso"].endswith("-08-15")


@pytest.mark.parametrize("span", [
    "it before 15 August", "that thing", "this one", "them", "the",
    "before Friday", "to launch", "15 August", "2026-08-15", "42",
])
def test_fragments_are_rejected(span: str) -> None:
    from app.memory.rules import valid_capture

    assert valid_capture(span) is None, span


@pytest.mark.parametrize("span,kept", [
    ("a landing page", "landing page"),      # article stripped, noun kept
    ("the pricing section", "pricing section"),
    ("16GB RAM", "16GB RAM"),
    ("at least 8 cores", "8 cores"),
])
def test_real_spans_survive_validation(span: str, kept: str) -> None:
    from app.memory.rules import valid_capture

    assert valid_capture(span) == kept


# --- BUG-3: conflicts compare normalized values -------------------------------


def test_restating_a_date_differently_is_not_a_conflict() -> None:
    """"15 Aug" then "15 August" is the same day, said twice."""
    state, handle = _ingest("deadline is 15 Aug")
    state, _ = _ingest("deadline is 15 August", state, handle)

    assert state.get("conflicts", []) == []
    assert state["reinforced"]["constraints.deadline"] == 2


def test_the_year_is_kept_when_stated() -> None:
    state = extract_state("I need it before 15 Aug 2026").model_dump()
    deadline = state["constraints"]["deadline"]
    assert deadline["iso"] == "2026-08-15"
    assert "year_inferred" not in deadline


def test_an_absent_year_infers_the_next_occurrence() -> None:
    """A deadline must never resolve into the past."""
    parsed = norm.normalize_date("15 Aug", now=datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert parsed["iso"] == "2027-08-15"
    assert parsed["year_inferred"] is True


def test_a_genuine_change_is_still_a_conflict() -> None:
    old = {"constraints": {"deadline": {"iso": "2026-08-15", "raw": "15 Aug"}}}
    new = {"constraints": {"deadline": {"iso": "2026-09-01", "raw": "1 Sep"}}}
    conflicts = detect_conflicts(old, new)
    assert len(conflicts) == 1
    assert conflicts[0]["field"] == "constraints.deadline"
    assert conflicts[0]["resolution"] == "latest_wins"


def test_conflict_comparison_ignores_surface_form() -> None:
    """Legacy rows hold raw strings; they must compare on meaning."""
    old = {"constraints": {"deadline": "15 Aug"}}
    new = {"constraints": {"deadline": "15 August"}}
    result = compare(old, new)
    assert result.conflicts == []
    assert result.reinforced == ["constraints.deadline"]


# --- the STORE-boundary invariant ---------------------------------------------


def test_duplicate_paths_are_refused_at_the_store_boundary() -> None:
    """The backstop: if a write ever bypasses the registry, it must not persist."""
    bad = {"constraints": {"budget_inr": 90000, "budget_inr_max": 75000}}
    with pytest.raises(canon.DuplicatePathError) as exc:
        canon.assert_no_duplicate_paths(bad)
    assert "constraints.budget.max" in str(exc.value)


def test_the_invariant_has_teeth_against_the_real_store(tmp_path) -> None:
    from sqlalchemy import create_engine

    from app.memory.storage import metadata

    engine = create_engine(f"sqlite:///{tmp_path/'inv.db'}")
    metadata.create_all(engine)
    store = MemoryStore(engine)

    with pytest.raises(canon.DuplicatePathError):
        store.save_state(
            "shm_x", None,
            {"constraints": {"budget": 1, "max_budget": 2}},
            "v1", "v1", user_id=1, session_tag="s",
        )


@pytest.mark.parametrize("text", [
    "My budget is under 75000 rupees",
    "I need it before 15 August",
    "name Ayaan, budget 2000, prefer email, deadline 15 Aug",
    "Book a flight from Pune to Goa, budget 8000, 2 passengers",
    "3 BHK in Baner, budget 90 lakh, contact whatsapp",
])
def test_no_canonical_path_appears_twice(text: str) -> None:
    """Property test: the invariant holds for everything the extractor emits."""
    state, _ = _ingest(text)
    canon.assert_no_duplicate_paths(state)


# --- determinism ---------------------------------------------------------------


def test_identical_input_yields_an_identical_handle() -> None:
    def run() -> str:
        state, handle = _ingest("My budget is under 75000 rupees")
        state, handle = _ingest("Update: budget is now 90000 rupees", state, handle)
        return handle

    assert run() == run()


def test_a_conflict_does_not_make_the_handle_time_varying() -> None:
    """A conflict record carries a wall-clock stamp; hashing it broke replay."""
    state, handle = _ingest("deadline is 15 Aug")
    state, h1 = _ingest("deadline is 1 September", state, handle)
    assert state["conflicts"], "this fixture must actually produce a conflict"

    state2, handle2 = _ingest("deadline is 15 Aug")
    state2, h2 = _ingest("deadline is 1 September", state2, handle2)
    assert h1 == h2


# --- quarantine ----------------------------------------------------------------


def test_a_free_text_claim_does_not_become_a_registry_field() -> None:
    """No declared field holds a favourite dinosaur, and none is invented."""
    state = extract_state("my favourite dinosaur is a stegosaurus").model_dump()
    for section in canon.ACTIVE_SECTIONS:
        if section == "dynamic":
            continue
        assert "stegosaurus" not in json.dumps(state[section]).lower()


def test_quarantine_records_why() -> None:
    """Every quarantine entry names the guard it failed."""
    state = extract_state("Max load per container is 24 tonnes.").model_dump()
    for entry in state["unmapped"].values():
        assert entry["reason"] in ("unknown_key", "rejected_value", "low_confidence")
        assert entry["value"]


def test_quarantine_never_reaches_the_handle() -> None:
    """Two states differing only in quarantine are the same state."""
    clean, h1 = initial_state(extract_state("budget 5000").model_dump())
    noisy_extract = extract_state("budget 5000").model_dump()
    noisy_extract["unmapped"] = {"facts.zzz": {"value": "x", "reason": "unknown_key"}}
    noisy, h2 = initial_state(noisy_extract)
    assert h1 == h2


# --- normalizers ---------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("₹75,000", 75000), ("75k", 75000), ("Rs. 75000", 75000),
    ("seventy five thousand", 75000), ("1.5 lakh", 150000),
    ("2 crore", 20000000), (75000, 75000),
])
def test_money_forms_normalize(raw, expected) -> None:
    assert norm.normalize_money(raw) == {"value": expected, "currency": "INR"}


def test_money_keeps_a_non_inr_currency() -> None:
    assert norm.normalize_money("$900") == {"value": 900, "currency": "USD"}


@pytest.mark.parametrize("raw", ["", "banana", None, [], -5, 0, True])
def test_money_rejects_non_money(raw) -> None:
    assert norm.normalize_money(raw) is None


@pytest.mark.parametrize("raw,iso", [
    ("15 Aug", "2026-08-15"), ("15 August", "2026-08-15"),
    ("15 Aug 2026", "2026-08-15"), ("2026-08-15", "2026-08-15"),
    ("Aug 15", "2026-08-15"), ("today", "2026-08-02"),
    ("tomorrow", "2026-08-03"), ("in 2 weeks", "2026-08-16"),
    ("next Friday", "2026-08-07"),
])
def test_date_forms_normalize(raw, iso) -> None:
    assert norm.normalize_date(raw, now=NOW)["iso"] == iso


@pytest.mark.parametrize("raw", ["", "banana", "the 40th of Smarch", None, 5])
def test_date_rejects_non_dates(raw) -> None:
    assert norm.normalize_date(raw, now=NOW) is None


@pytest.mark.parametrize("raw,mode", [
    ("EMAIL", "email"), ("e-mail", "email"), ("mail", "email"),
    ("email me", "email"), ("phone", "phone"), ("call", "phone"),
    ("text", "sms"), ("WhatsApp", "whatsapp"),
])
def test_contact_enum_folds_synonyms(raw, mode) -> None:
    assert canon.canonicalize("contact_mode", raw) == ("preferences.contact_mode", mode)


@pytest.mark.parametrize("raw", ["pigeon", "carrier owl", "", None, 42])
def test_unknown_enum_values_are_rejected(raw) -> None:
    assert canon.canonicalize("contact_mode", raw) is None


def test_strings_are_trimmed_and_collapsed() -> None:
    assert norm.normalize_string("  Koregaon   Park.  ") == "Koregaon Park"


# --- registry hygiene ----------------------------------------------------------


def test_every_field_declares_a_working_normalizer() -> None:
    for spec in canon.REGISTRY:
        assert callable(spec.normalizer), spec.path
        assert spec.normalizer("") in (None, "", [], {}), spec.path


def test_no_alias_is_claimed_by_two_fields() -> None:
    """An ambiguous alias would silently route a fact to the wrong field."""
    seen: dict[str, str] = {}
    for spec in canon.REGISTRY:
        for alias in spec.aliases:
            assert alias not in seen or seen[alias] == spec.path, (
                f"alias {alias!r} claimed by {seen.get(alias)} and {spec.path}"
            )
            seen[alias] = spec.path


def test_every_path_is_addressable_by_its_own_name() -> None:
    for spec in canon.REGISTRY:
        assert canon.resolve(spec.path) is spec, spec.path


def test_confidence_floor_rejects_an_unsure_tier() -> None:
    assert canon.canonicalize("name", "Ayaan", confidence=0.3) is None
    assert canon.canonicalize("name", "Ayaan", confidence=0.9) == ("facts.name", "Ayaan")


def test_sensitive_fields_are_marked() -> None:
    """PII has to be labelled for a minimal-disclosure claim to mean anything."""
    for path in ("facts.name", "facts.email", "facts.phone", "facts.age"):
        assert canon.BY_PATH[path].sensitivity == canon.PII, path
