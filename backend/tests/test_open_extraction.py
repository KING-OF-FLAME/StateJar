"""Acceptance tests for the open extractor — one per row of the battery.

The registry can only hold what someone declared, so anything else went to
`_unmapped` and was never seen again. These assert the other half: a concept
nobody declared becomes a dynamic field with the same lifecycle, the same
invariant, and the same place in the handle.

Tier 1 only. The LLM tier generalises further, but the demo and the free tier
run without a key, so a row that needs tier 3 to extract anything at all is a
gap in the rules — not a pass.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from app.config import get_settings
from app.memory.extractor import extract_rules, extract_state
from app.memory.retriever import retrieve_minimum
from app.memory.versioning import evolve_state, initial_state
from app.schema import canonical as canon
from app.schema import dynamic as dyn


@pytest.fixture(autouse=True)
def _rules_only(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("EXTRACTOR_MODE", "rules")
    monkeypatch.setenv("EXTRACTOR_LLM_FALLBACK", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _first(state: dict, text: str) -> tuple[dict, str]:
    return initial_state(extract_state(text).model_dump())


def _then(state: dict, handle: str, text: str) -> tuple[dict, str]:
    extracted, _ = extract_rules(text, state)
    return evolve_state(state, extracted.model_dump(), handle)


def _dynamic(state: dict) -> dict:
    return state.get(dyn.SECTION) or {}


def _paths(state: dict) -> set[str]:
    out = set()
    for section in canon.ACTIVE_SECTIONS:
        out.update(canon.leaf_paths_in(state.get(section), section))
    return out


# --- the tonnage row ----------------------------------------------------------


def test_a_load_limit_is_a_quantity_not_a_budget() -> None:
    state, _ = _first({}, "Max load per container is 24 tonnes.")
    assert "constraints.budget.max" not in _paths(state)

    entry = _dynamic(state)["load_per_container"]["max"]
    assert entry["type"] == "quantity"
    assert entry["value"] == 24_000_000        # 24 tonnes in the base unit
    assert entry["unit"] == "g"
    assert "currency" not in entry


def test_the_same_limit_said_differently_updates_one_field() -> None:
    """"max load per container" and "container load limit" are one slot."""
    state, handle = _first({}, "Max load per container is 24 tonnes.")
    state, _ = _then(state, handle, "Update: container load limit is now 26 tonnes.")

    limits = [p for p in _paths(state) if p.startswith("dynamic.load")]
    assert len(limits) == 1, f"one concept, one path — got {limits}"
    assert canon.read_path(state, limits[0])["value"] == 26_000_000
    assert [h["value"]["value"] for h in state["history"]] == [24_000_000]


# --- the shipment row ---------------------------------------------------------


def test_three_kinds_in_one_sentence_land_in_three_fields() -> None:
    state, _ = _first(
        {}, "Shipment weighs 1,240 kg, insured for $8,500, transit time 11 days."
    )
    fields = {
        canon.read_path(state, p)["type"]: canon.read_path(state, p)
        for p in _paths(state)
    }
    assert fields["quantity"]["value"] == 1_240_000      # 1,240 kg in grams
    assert fields["money"] == {"type": "money", "value": 8500, "currency": "USD",
                               "concept": fields["money"]["concept"]}
    assert fields["duration"]["value"] == 950_400        # 11 days in seconds
    assert "constraints.budget.max" not in _paths(state)


def test_a_correction_in_another_unit_is_not_a_conflict() -> None:
    """1,240 kg and 1.24 tonnes are the same measurement, said twice."""
    state, handle = _first({}, "Shipment weighs 1,240 kg.")
    state, _ = _then(state, handle, "Correction: shipment weighs 1.24 tonnes.")
    assert state.get("conflicts", []) == []
    assert state["reinforced"]


# --- the poultry row ----------------------------------------------------------


def test_a_pronoun_is_not_a_name_and_a_grouped_number_is_not_truncated() -> None:
    state, _ = _first(
        {}, "I run a poultry farm in Latur. Current flock is 4,200 birds "
            "and feed conversion ratio is 1.68."
    )
    assert canon.read_path(state, "facts.name") is None
    assert _dynamic(state)["flock"]["current"]["value"] == 4200
    assert _dynamic(state)["feed_conversion_ratio"]["value"] == 1.68


# --- the kiln row -------------------------------------------------------------


def test_two_cone_numbers_stay_distinct() -> None:
    """Cone 06 is a different firing from cone 6; a leading zero is a code."""
    state, _ = _first(
        {}, "Kiln firing schedule: bisque at cone 06, glaze at cone 6, "
            "hold 20 minutes at peak."
    )
    bisque = _dynamic(state)["bisque"]
    glaze = _dynamic(state)["glaze"]
    assert bisque["value"] != glaze["value"]
    assert bisque["value"] == "cone 06"
    assert glaze["value"] == 6


def test_a_message_outside_every_declared_field_produces_no_unresolved_noise() -> None:
    """35 registry fields listed as "Not provided" is not extraction."""
    state, _ = _first(
        {}, "Kiln firing schedule: bisque at cone 06, glaze at cone 6, "
            "hold 20 minutes at peak."
    )
    assert not state.get("unresolved")
    assert _dynamic(state), "the message plainly stated things"


# --- the booking rows ---------------------------------------------------------


def test_a_start_and_an_end_are_two_fields() -> None:
    state, _ = _first({}, "Booking starts 12 September and ends 19 September.")
    booking = _dynamic(state)["booking"]
    assert booking["start"]["iso"].endswith("-09-12")
    assert booking["end"]["iso"].endswith("-09-19")
    # a qualified date is never the unqualified deadline
    assert canon.read_path(state, "constraints.deadline") is None


def test_an_update_naming_a_qualifier_leaves_the_other_intact() -> None:
    """The row that destroyed a start date: "push the end date"."""
    state, handle = _first({}, "Booking starts 12 September and ends 19 September.")
    state, _ = _then(state, handle, "Push the end date to 22 September.")

    booking = _dynamic(state)["booking"]
    assert booking["start"]["iso"].endswith("-09-12"), "start must be untouched"
    assert booking["end"]["iso"].endswith("-09-22")


# --- retraction ---------------------------------------------------------------


def test_a_retraction_removes_the_field_from_active_state() -> None:
    state, handle = _first({}, "Insured value is $8,500 and transit time is 11 days.")
    assert any("insur" in p for p in _paths(state))

    state, _ = _then(state, handle,
                     "Actually ignore the insurance figure, we are not insuring this one.")
    assert not any("insur" in p for p in _paths(state))
    assert any(h["reason"] == "retracted" for h in state["history"])


def test_a_retracted_field_is_not_sent_to_the_model() -> None:
    """A value still in active state is still disclosed, so logging is not enough."""
    state, handle = _first({}, "Insured value is $8,500 and transit time is 11 days.")
    state, _ = _then(state, handle, "Actually ignore the insurance figure.")

    subset = retrieve_minimum("tell me about the shipment", state)["subset"]
    import json
    assert "8500" not in json.dumps(subset)


# --- the GST row --------------------------------------------------------------


def test_turnover_is_not_a_shopping_budget() -> None:
    state, _ = _first(
        {}, "Mera GST number 27ABCDE1234F1Z5 hai, filing quarterly karta hoon, "
            "turnover pichle saal 42 lakh tha."
    )
    assert "constraints.budget.max" not in _paths(state)
    money = [canon.read_path(state, p) for p in _paths(state)
             if (canon.read_path(state, p) or {}).get("type") == "money"]
    assert money and money[0]["value"] == 4_200_000


# --- questions and chit-chat --------------------------------------------------


def test_a_question_creates_no_fields() -> None:
    state, _ = _first({}, "What's the max load again?")
    assert _paths(state) == set()


@pytest.mark.parametrize("text", [
    "the area is nice and quiet",
    "hi hello there",
    "tell me a joke",
    "thanks, that works",
    "please explain how handles work",
])
def test_open_extraction_does_not_turn_conversation_into_state(text: str) -> None:
    state, _ = _first({}, text)
    assert _paths(state) == set(), f"{text!r} -> {_paths(state)}"


# --- dynamic fields are first-class -------------------------------------------


def test_dynamic_fields_are_part_of_the_handle() -> None:
    a, ha = _first({}, "Max load per container is 24 tonnes.")
    b, hb = _first({}, "Max load per container is 26 tonnes.")
    assert ha != hb, "a different value must be a different state"


def test_dynamic_fields_are_retrievable() -> None:
    state, _ = _first({}, "Max load per container is 24 tonnes.")
    subset = retrieve_minimum("what is the load limit", state)["subset"]
    assert subset.get(dyn.SECTION), subset


def test_dynamic_fields_hold_the_duplicate_path_invariant() -> None:
    state, _ = _first(
        {}, "Shipment weighs 1,240 kg, insured for $8,500, transit time 11 days."
    )
    canon.assert_no_duplicate_paths(state)


def test_unmapped_is_now_only_for_guard_failures() -> None:
    """Unfamiliar is not the same as invalid. Only the second is quarantine."""
    state, _ = _first({}, "Max load per container is 24 tonnes.")
    for entry in (state.get("_unmapped") or {}).values():
        assert entry["reason"] in ("rejected_value", "low_confidence")


# --- determinism --------------------------------------------------------------


BATTERY = [
    "Max load per container is 24 tonnes.",
    "Update: container load limit is now 26 tonnes.",
    "Shipment weighs 1,240 kg, insured for $8,500, transit time 11 days.",
    "I run a poultry farm in Latur. Current flock is 4,200 birds "
    "and feed conversion ratio is 1.68.",
    "Kiln firing schedule: bisque at cone 06, glaze at cone 6, hold 20 minutes at peak.",
    "Booking starts 12 September and ends 19 September.",
    "Push the end date to 22 September.",
    "Mera GST number 27ABCDE1234F1Z5 hai, filing quarterly karta hoon, "
    "turnover pichle saal 42 lakh tha.",
    "What's the max load again?",
]


def test_the_battery_is_deterministic_across_cold_runs() -> None:
    """Three runs, identical handles. Dynamic concepts are in the hash, so
    concept naming has to be deterministic too — which is why reuse is done
    by content-word containment rather than by similarity."""
    def run() -> list[str]:
        state, handle = initial_state(extract_state(BATTERY[0]).model_dump())
        handles = [handle]
        for message in BATTERY[1:]:
            extracted, _ = extract_rules(message, state)
            state, handle = evolve_state(state, extracted.model_dump(), handle)
            handles.append(handle)
        return handles

    first, second, third = run(), run(), run()
    assert first == second == third


def test_the_battery_never_holds_two_values_for_one_path() -> None:
    state, handle = initial_state(extract_state(BATTERY[0]).model_dump())
    canon.assert_no_duplicate_paths(state)
    for message in BATTERY[1:]:
        extracted, _ = extract_rules(message, state)
        state, handle = evolve_state(state, extracted.model_dump(), handle)
        canon.assert_no_duplicate_paths(state)


# --- regression guards from earlier passes ------------------------------------


def test_date_surface_forms_still_reinforce() -> None:
    state, handle = _first({}, "deadline is 3rd Nov")
    state, _ = _then(state, handle, "deadline is November 3")
    assert state.get("conflicts", []) == []


def test_indian_numbering_still_parses() -> None:
    state, _ = _first({}, "my budget is 42 lakh")
    assert canon.read_path(state, "constraints.budget.max")["value"] == 4_200_000
