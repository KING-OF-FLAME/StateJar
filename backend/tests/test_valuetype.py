"""Type-compatibility guard, number parsing, degenerate-value rejection.

Day 1 of the generality work. Every case here is drawn from the battery that
was run against the deployed playground, where the alias matcher fired on
lexical proximity and never checked whether the value could be the thing the
field claims to hold.
"""

from __future__ import annotations

import random

import pytest

from app.memory.extractor import extract_state
from app.schema import canonical as canon
from app.schema import valuetype as vt


def _flat(state: dict) -> dict:
    out = {}
    for section in canon.ACTIVE_SECTIONS:
        for path in canon.leaf_paths_in(state.get(section), section):
            value = canon.read_path(state, path)
            if isinstance(value, dict):
                value = value.get("value", value.get("iso", value))
            out[path] = value
    return out


# --- Fix 2: number parsing with grouping separators ---------------------------


@pytest.mark.parametrize("text,expected", [
    ("4200", 4200),
    ("4,200", 4200),           # was parsed as 4
    ("1,240", 1240),           # was parsed as 1
    ("1,240,000", 1240000),
    ("12,40,000", 1240000),    # Indian grouping
    ("1,24,000", 124000),
    ("1 240", 1240),           # space grouping
    ("1 240", 1240),      # narrow no-break space
    ("1.24", 1.24),
    ("12,40,000.50", 1240000.5),
])
def test_grouped_numbers_parse(text: str, expected: float) -> None:
    assert vt.parse_number(text) == expected


@pytest.mark.parametrize("text", ["1,2345", "", "abc", "1,,2", ",200", None])
def test_invalid_grouping_is_rejected_not_mangled(text) -> None:
    """A string that merely contains commas must not become a number.

    Stripping separators blindly is how "1,2345" would silently become 12345.
    """
    assert vt.parse_number(text) is None


@pytest.mark.parametrize("style", ["plain", "western", "indian", "space"])
def test_parse_format_round_trips(style: str) -> None:
    """Property: parse(format(n)) == n, across every grouping style."""
    rng = random.Random(20260803)
    values = [rng.randint(0, 10**9) for _ in range(300)]
    values += [0, 1, 999, 1000, 1240, 4200, 100000, 1240000, 10**9]
    for n in values:
        rendered = vt.format_number(n, style)
        assert vt.parse_number(rendered) == n, f"{style}: {rendered!r} -> {n}"


def test_scale_words_survive() -> None:
    """Indian magnitude words are the regression guard from the last pass."""
    assert vt.classify("42 lakh", context="turnover").number == 4_200_000
    assert vt.classify("2 crore", context="budget").number == 20_000_000
    assert vt.classify("5k", context="budget").number == 5_000


def test_the_k_of_kg_is_not_a_scale() -> None:
    """1,240 kg became 1,240,000 because "k" matched inside "kg"."""
    reading = vt.classify("1,240 kg", context="Shipment weighs")
    assert reading.kind == vt.QUANTITY
    assert reading.number == 1240
    assert reading.unit == "kg"


# --- Fix 1: classification and the compatibility guard ------------------------


@pytest.mark.parametrize("span,context,kind", [
    ("24 tonnes", "Max load per container is", vt.QUANTITY),
    ("1,240 kg", "Shipment weighs", vt.QUANTITY),
    ("$8,500", "insured for", vt.MONEY),
    ("11 days", "transit time", vt.DURATION),
    ("20 minutes", "hold at peak", vt.DURATION),
    ("4,200 birds", "Current flock is", vt.COUNT),
    ("1.68", "feed conversion ratio is", vt.RATIO),
    ("27ABCDE1234F1Z5", "GST number", vt.IDENTIFIER),
    ("12 September", "Booking starts", vt.DATE),
    ("42 lakh", "turnover pichle saal", vt.MONEY),
    ("2000", "budget under", vt.MONEY),
    ("15%", "margin of", vt.PERCENT),
])
def test_classification(span: str, context: str, kind: str) -> None:
    assert vt.classify(span, context=context).kind == kind


def test_a_bare_number_is_not_money() -> None:
    """No currency marker, no money noun, no magnitude word — not money.

    Default-to-INR on a bare number is the single line that produced the
    tonnage bug, so its absence is asserted directly.
    """
    assert vt.classify("24", context="max load is").kind != vt.MONEY
    assert vt.detect_currency("24 tonnes") is None
    assert vt.detect_currency("max 4999") is None


@pytest.mark.parametrize("span,context", [
    ("24 tonnes", "Max load per container is"),
    ("1,240 kg", "Shipment weighs"),
    ("11 days", "transit time"),
    ("4,200 birds", "Current flock is"),
    ("12 September", "Booking starts"),
    ("27ABCDE1234F1Z5", "GST number"),
])
def test_incompatible_values_never_reach_a_money_field(span, context) -> None:
    assert canon.canonicalize("budget", span, context=context) is None


def test_money_never_reaches_a_quantity_field() -> None:
    assert canon.canonicalize("quantity", "$8,500", context="insured for") is None


def test_a_date_never_reaches_a_money_field() -> None:
    assert canon.canonicalize("budget", "20 September") is None


def test_a_quantity_never_reaches_a_date_field() -> None:
    assert canon.canonicalize("deadline", "24 tonnes") is None


def test_an_explicit_assignment_still_works() -> None:
    """The guard stops values being vacuumed in, not direct assignment.

    Naming the field is itself a money signal; if it were not, `budget: 75000`
    would be refused and the guard would have replaced one bug with another.
    """
    assert canon.canonicalize("budget", "75000") == (
        "constraints.budget.max", {"value": 75000, "currency": "INR"}
    )


def test_units_beat_an_explicit_assignment() -> None:
    """...but naming the field cannot override the value's own unit."""
    assert canon.canonicalize("budget", "24 tonnes") is None


# --- Fix 3: degenerate values -------------------------------------------------


@pytest.mark.parametrize("key,value", [
    ("area", "area"),                # "What's the max load again?" -> area: "area"
    ("name", "name"),
    ("city", "city"),
    ("name", "I"),                   # "I run a poultry farm" -> name: "I"
    ("name", "we"),
    ("city", "there"),
    ("role", "that"),
    ("organization", "not provided"),
    ("area", "n/a"),
    ("name", "   "),
])
def test_degenerate_values_are_refused(key: str, value: str) -> None:
    assert canon.canonicalize(key, value) is None


def test_a_field_alias_is_not_a_value() -> None:
    """`location: "town"` is the field naming itself with a synonym."""
    assert canon.canonicalize("city", "town") is None
    assert canon.canonicalize("organization", "company") is None


def test_none_is_a_value_not_a_refusal() -> None:
    """For `no_ui_libs`, "none" is the answer. Over-broad stopwords ate it."""
    assert canon.canonicalize("no_ui_libs", "none") == ("constraints.no_ui_libs", "none")


# --- end to end: the battery rows Day 1 covers --------------------------------


def test_tonnage_is_never_stored_as_rupees() -> None:
    got = _flat(extract_state("Max load per container is 24 tonnes.").model_dump())
    assert "constraints.budget.max" not in got, got


def test_shipment_weight_is_never_money() -> None:
    state = extract_state(
        "Shipment weighs 1,240 kg, insured for $8,500, transit time 11 days."
    ).model_dump()
    got = _flat(state)
    assert got.get("constraints.budget.max") != 1240000
    assert got.get("constraints.budget.max") != 1240


def test_a_pronoun_is_never_a_name() -> None:
    got = _flat(extract_state(
        "I run a poultry farm in Latur. Current flock is 4,200 birds "
        "and feed conversion ratio is 1.68."
    ).model_dump())
    assert got.get("facts.name") != "I"
    assert got.get("constraints.quantity") != 4      # 4,200 was parsed as 4


def test_a_question_asserts_nothing() -> None:
    got = _flat(extract_state("What's the max load again?").model_dump())
    assert got == {}, got


def test_a_refused_write_leaves_evidence() -> None:
    """A guard failure is recorded, not swallowed — that is the feedback loop."""
    state = extract_state(
        "Update: container load limit is now 26 tonnes."
    ).model_dump()
    assert state["unmapped"], "a refused value must be recorded"
    assert all(
        entry["reason"] in ("unknown_key", "rejected_value", "low_confidence")
        for entry in state["unmapped"].values()
    )


def test_day1_leaves_the_tonnage_message_unextracted() -> None:
    """Documents the state of play, so the Fix 4 change is visible as a change.

    After the guards, nothing in this message is stored wrongly — but nothing
    is stored at all either, because no rule claims "container load limit".
    Opening the extractor (Fix 4) is what turns this into a dynamic field; the
    guards only stop it becoming a budget in the meantime.
    """
    state = extract_state("Max load per container is 24 tonnes.").model_dump()
    assert _flat(state) == {}
    assert "constraints.budget.max" not in _flat(state)


# --- regression guards from the previous pass ---------------------------------


def test_indian_numbering_still_works() -> None:
    got = _flat(extract_state("turnover pichle saal 42 lakh tha").model_dump())
    assert got["constraints.budget.max"] == 4_200_000


def test_date_surface_forms_still_equivalent() -> None:
    a = extract_state("deadline is 3rd Nov").model_dump()
    b = extract_state("deadline is November 3").model_dump()
    assert a["constraints"]["deadline"]["iso"] == b["constraints"]["deadline"]["iso"]
