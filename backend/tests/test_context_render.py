"""The compact model-facing renderer, and the boundary it must not cross.

Two separate risks, tested separately.

The first is silent loss. A renderer that drops a field looks exactly like a
saving — the token count falls, nothing errors, and the only symptom is an
answer that is missing something. So the contract is stated as an equality
against the same path walk the retriever uses to build `subset_keys`, not as a
spot check of a few fields.

The second is scope. This is presentation only: the stored state, the
canonical bytes and the handle must be byte-identical whether or not the
renderer exists. That is asserted here rather than assumed, because "it only
changes the prompt" is exactly what someone would say right before a handle
moved.
"""

from __future__ import annotations

import json

from app.llm.gateway import build_system_context, render_compact
from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.extractor import extract_state
from app.memory.handle import generate_handle
from app.memory.retriever import retrieve_minimum
from app.memory.versioning import UNHASHED_KEYS, evolve_state
from app.schema import canonical as canon

SUBSET = {
    "facts": {"name": "Meera Nair", "email": "meera@reliefnet.org"},
    "constraints": {
        "budget": {"max": {"value": 2200000, "currency": "INR"}},
        "deadline": {"iso": "2026-08-14", "raw": "14 August",
                     "ambiguous": False, "year_inferred": True},
        "requirements": ["cold chain", "night driving"],
    },
    "dynamic": {
        "truck_count": {"concept": "truck count", "type": "count", "value": 5},
        "capacity_per_truck": {"concept": "capacity per truck", "type": "quantity",
                               "unit": "g", "value": 8000000},
        "first_convoy_departs": {
            "before": {"concept": "first convoy departs", "iso": "2026-08-14",
                       "raw": "14 August", "type": "date"},
        },
    },
    "unresolved": [{"field": "second_warehouse", "reason": "not provided"}],
}


def _paths(subset: dict) -> set[str]:
    """The same walk the retriever uses to produce `subset_keys`."""
    out = set()
    for section, block in subset.items():
        if section in ("unresolved", "_unmapped") or not isinstance(block, dict):
            continue
        out.update(canon.leaf_paths_in(block, section))
    return out


# --- nothing may be dropped ---------------------------------------------------


def test_every_field_in_the_subset_appears_in_the_render() -> None:
    """The contract. Not a sample — every path, or the test fails."""
    rendered = render_compact(SUBSET)
    labels = {line.split(":", 1)[0] for line in rendered.splitlines()}
    missing = sorted(_paths(SUBSET) - labels)
    assert not missing, f"renderer dropped {missing}"


def test_one_line_per_field_and_no_extras() -> None:
    rendered = render_compact(SUBSET)
    lines = rendered.splitlines()
    # every state path, plus the one unresolved entry
    assert len(lines) == len(_paths(SUBSET)) + 1
    assert len(lines) == len(set(lines)), "a field was rendered twice"


def test_values_survive_verbatim() -> None:
    rendered = render_compact(SUBSET)
    for expected in ("Meera Nair", "meera@reliefnet.org", "2200000", "5",
                     "8000000", "2026-08-14", "cold chain", "night driving"):
        assert expected in rendered, f"{expected!r} was lost"


def test_units_and_currency_are_kept() -> None:
    """"8000000" and "8000000 g" are different facts. Dropping the unit is how
    a saving becomes a wrong answer."""
    rendered = render_compact(SUBSET)
    assert "8000000 g" in rendered
    assert "INR 2200000" in rendered


def test_a_qualifier_stays_in_the_path() -> None:
    """`first_convoy_departs.before` is not the same field as
    `first_convoy_departs`."""
    assert "dynamic.first_convoy_departs.before:" in render_compact(SUBSET)


def test_declines_and_unresolved_are_kept() -> None:
    """A refusal with a stated reason is the differentiator, not overhead."""
    rendered = render_compact({
        **SUBSET,
        "_unmapped": {"constraints.budget.max": {"value": "now",
                                                 "reason": "rejected_value"}},
    })
    assert "unresolved.second_warehouse" in rendered
    assert "not provided" in rendered
    assert "declined.constraints.budget.max" in rendered
    assert "rejected_value" in rendered


def test_date_caveats_appear_only_when_set() -> None:
    on = render_compact({"constraints": {"deadline": {
        "iso": "2026-08-14", "raw": "14 Aug", "ambiguous": True}}})
    off = render_compact({"constraints": {"deadline": {
        "iso": "2026-08-14", "raw": "14 Aug", "ambiguous": False}}})
    assert "ambiguous" in on
    assert "ambiguous" not in off, "a line of false flags on every date is pure cost"


def test_an_unknown_envelope_shape_degrades_to_verbose_not_missing() -> None:
    """A value shape the renderer has never seen must still be disclosed."""
    rendered = render_compact({"dynamic": {"odd": {"lo": 1, "hi": 9}}})
    assert "dynamic.odd" in rendered
    assert "1" in rendered and "9" in rendered


def test_render_is_smaller_than_the_json_it_replaces() -> None:
    """The point of the change. Not a target — just that it is not a
    regression dressed as one."""
    compact = render_compact(SUBSET)
    as_json = json.dumps(SUBSET, ensure_ascii=False, sort_keys=True)
    assert len(compact) < len(as_json)


# --- presentation only: the handle must not move ------------------------------


TURNS = [
    "Relief operation for Wayanad district. Displaced families is 4,200.",
    "Truck count is 3, capacity per truck is 8 tonnes.",
    "Sanctioned budget is 22 lakh rupees.",
    "Update: truck count is now 5.",
]


def _run() -> tuple[dict, str]:
    state = handle = None
    for msg in TURNS:
        extracted = extract_state(msg).model_dump()
        if state is None:
            state = json.loads(canonicalize(extracted))
            handle = generate_handle(canonicalize(extracted), SCHEMA_VERSION, NORM_VERSION)
        else:
            state, handle = evolve_state(state, extracted, handle)
            state.pop("parent_handle", None)
    return state, handle


def test_rendering_the_context_does_not_change_the_handle() -> None:
    """Building a prompt is a read. If this ever fails, the renderer reached
    into the stored state instead of copying out of it."""
    state, handle = _run()
    before = json.dumps(state, sort_keys=True)

    retrieved = retrieve_minimum("what is my budget?", state)
    build_system_context(handle, retrieved["subset"])
    render_compact(retrieved["subset"])

    assert json.dumps(state, sort_keys=True) == before, "state mutated by rendering"
    assert generate_handle(canonicalize(state), SCHEMA_VERSION, NORM_VERSION) == \
        generate_handle(canonicalize(json.loads(before)), SCHEMA_VERSION, NORM_VERSION)


def test_the_same_conversation_still_produces_one_handle() -> None:
    """Two independent runs of the same input, with rendering in between.

    The bytes compared are the hashed ones only. A history record carries the
    wall-clock instant the change was noticed, so the full record differs
    between runs by design — that is precisely why `UNHASHED_KEYS` exists, and
    comparing the whole thing would be testing the clock.
    """
    state_a, handle_a = _run()
    retrieve_minimum("anything at all", state_a)
    build_system_context(handle_a, {"facts": {"name": "x"}})
    state_b, handle_b = _run()

    assert handle_a == handle_b
    hashed = lambda s: canonicalize({k: v for k, v in s.items() if k not in UNHASHED_KEYS})
    assert hashed(state_a) == hashed(state_b)
