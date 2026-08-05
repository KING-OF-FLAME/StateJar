"""A span may only fill a slot its own text supports.

Reported from live input: `city` came back "Senior Software", `name` had been
overwritten with "Mumbai". Both values were one slot away from where they
belonged, and the second turn destroyed two correct facts from the first.

The cause is that `find_name` and `find_city` capture with the *same* pattern
(`_CITY` is character-for-character `_NAME`), so nothing about a span says
whether it is a person or a place. The only thing choosing the slot is the
trigger word next to it — "I'm ..." for a name, "from ..." for a city — and
ordinary English produces both triggers constantly without naming anybody:

    "I'm switching from Senior Software Engineer to Engineering Manager"
     ^^^^                ^^^^^^^^^^^^^^^^^^^^^^^

Two spans in that sentence sit behind identity triggers. Neither is an
identity. The two-word capture cap then truncates "Senior Software Engineer"
mid-phrase and stores the fragment.

These tests state the invariant the module is supposed to have: the evidence
that binds a span to a slot must come from the span, not from its position
after a trigger. A span that cannot be shown to belong is refused — an absent
field is recoverable, a confidently wrong one is not (README.md:71, "It refuses
to guess").
"""

from __future__ import annotations

from app.memory import rules
from app.memory.extractor import extract_rules
from app.memory.versioning import evolve_state, initial_state


def _state(text: str, prior: dict | None = None) -> dict:
    return extract_rules(text, prior)[0].model_dump()


def _facts(text: str) -> dict:
    return _state(text).get("facts") or {}


# --- the exact reported repro -------------------------------------------------

TURN_1 = "My name is Rahul Sharma and I'm from Pune"
TURN_2 = ("I'm Mumbai based now, switching from Senior Software Engineer "
          "to Engineering Manager")


def test_reported_repro_does_not_rotate_identity_fields() -> None:
    """The verbatim two-turn sequence that produced the report.

    Before the fix this ended with name="Mumbai" and city="Senior Software":
    the name slot held a city and the city slot held half a job title.
    """
    state, handle = initial_state(_state(TURN_1))
    assert state["facts"]["name"] == "Rahul Sharma"
    assert state["facts"]["city"] == "Pune"

    state, _ = evolve_state(state, _state(TURN_2, state), handle)

    assert state["facts"]["name"] == "Rahul Sharma", (
        "an established name was overwritten by a value from a sentence that "
        "names no person"
    )
    assert state["facts"].get("city") != "Senior Software", (
        "half a job title was stored as a city"
    )


def test_job_change_is_not_a_relocation() -> None:
    """"from X to Y" is a transition frame, not a locative one."""
    assert rules.find_city(
        "switching from Senior Software Engineer to Engineering Manager"
    ) is None


def test_a_truncated_phrase_is_not_a_place() -> None:
    """The capture takes at most two words. When the phrase continues past
    them the capture is a fragment, and a fragment is not evidence."""
    assert rules.find_city("moved from Senior Software Engineer") is None
    assert rules.find_city("from Business Development Manager") is None
    # the same span, complete, is still found
    assert rules.find_city("moved from Pune") == "Pune"
    assert rules.find_city("I'm from New Delhi") == "New Delhi"


def test_a_place_behind_a_name_trigger_is_not_a_name() -> None:
    """"Mumbai" in "I'm Mumbai based" is bound to `based`, which is closer and
    more specific evidence than the "I'm" in front of it."""
    assert rules.find_name("I'm Mumbai based now") is None
    assert rules.find_name("I'm Pune based") is None
    assert rules.find_name("I'm Bangalore born and raised") is None


def test_the_place_still_lands_in_the_city_slot() -> None:
    """Refusing the wrong slot must not lose the fact — the span carries
    locative evidence, so it belongs to `city`."""
    assert _facts("I'm Mumbai based now")["city"] == "Mumbai"
    assert "name" not in _facts("I'm Mumbai based now")


def test_a_verb_is_not_a_name() -> None:
    """"I'm switching ..." is a progressive verb, not an introduction. This is
    grammar, not a list of words: any participle behaves the same way."""
    for text in ("I'm switching jobs", "I'm relocating soon",
                 "I'm joining a startup", "I'm interviewing tomorrow"):
        assert rules.find_name(text) is None, text


def test_real_introductions_still_work() -> None:
    """The guard must not cost the cases the rule exists for."""
    assert rules.find_name("My name is Rahul Sharma") == "Rahul Sharma"
    assert rules.find_name("I'm Ayaan") == "Ayaan"
    assert rules.find_name("I am Meera Nair") == "Meera Nair"
    assert rules.find_name("call me Sanjana") == "Sanjana"
    assert rules.find_name("mera naam Vikram hai") == "Vikram"


def test_real_cities_still_work() -> None:
    assert rules.find_city("I'm from Pune") == "Pune"
    assert rules.find_city("based in Mumbai") == "Mumbai"
    assert rules.find_city("living in Navi Mumbai") == "Navi Mumbai"
    assert rules.find_city("Pune se") == "Pune"


# --- rotated and shuffled variants --------------------------------------------


def test_rotated_variants_never_fill_an_identity_slot() -> None:
    """Same two spans, different orders. None of these name a person or a
    place, so none of them may write one."""
    for text in (
        "switching from Senior Software Engineer to Engineering Manager, "
        "I'm Mumbai based now",
        "I'm moving from Senior Software Engineer to Product Manager",
        "promoted from Senior Software Engineer",
        "I'm transitioning from Data Analyst to Data Scientist",
    ):
        facts = _facts(text)
        assert facts.get("city") not in (
            "Senior Software", "Data Analyst", "Business Development"
        ), f"{text!r} -> city={facts.get('city')!r}"


def test_sequential_overwrites_of_one_field_still_work() -> None:
    """Latest-wins is correct when the later turn really does state the field.
    The fix must not freeze a field at its first value."""
    state, handle = initial_state(_state("My name is Rahul Sharma"))
    assert state["facts"]["name"] == "Rahul Sharma"

    for stated, expected in (("Actually my name is Rahul Verma", "Rahul Verma"),
                             ("call me Raj", "Raj")):
        state, handle = evolve_state(state, _state(stated, state), handle)
        assert state["facts"]["name"] == expected, stated


def test_city_updates_still_replace_the_old_city() -> None:
    state, handle = initial_state(_state("I'm from Pune"))
    assert state["facts"]["city"] == "Pune"
    state, _ = evolve_state(state, _state("I'm based in Mumbai now", state), handle)
    assert state["facts"]["city"] == "Mumbai"


# --- the update path's own guard ----------------------------------------------


def test_update_path_refuses_a_value_the_field_cannot_hold() -> None:
    """`_merge` used to write any incoming value straight onto the path, so a
    value that could never have been written as a *first* write could still
    arrive as an update. The guard runs on both paths now, and a refusal is
    recorded rather than dropped."""
    state, handle = initial_state(_state("Deadline is 15 August"))
    assert state["constraints"]["deadline"] is not None

    forged = {"constraints": {"deadline": "not a date at all"}}
    merged, _ = evolve_state(state, forged, handle)

    assert merged["constraints"]["deadline"] != "not a date at all", (
        "the update path wrote a value the field's own normalizer refuses"
    )
    assert any("deadline" in key for key in (merged.get("_unmapped") or {})), (
        "a refused update must say so — silence is indistinguishable from a "
        "value that was never sent"
    )


def test_refusal_records_a_reason() -> None:
    state, handle = initial_state(_state("Deadline is 15 August"))
    merged, _ = evolve_state(
        state, {"constraints": {"deadline": "not a date at all"}}, handle
    )
    entry = next(v for k, v in merged["_unmapped"].items() if "deadline" in k)
    assert entry.get("reason"), "a refusal with no reason is not auditable"


# --- the same construct elsewhere ---------------------------------------------
#
# The two-word cap is not unique to name and city. Every rule that captures a
# proper noun uses it, and every one of them truncates the same way.


def test_an_employer_is_not_truncated() -> None:
    """"Tata Consultancy" is a different company from "Tata Consultancy
    Services". A half-right value is still a wrong value."""
    assert rules.find_employer("I work at Tata Consultancy Services") is None
    assert rules.find_employer("working at Infosys") == "Infosys"
    assert rules.find_employer("I am at Google") == "Google"


def test_a_route_destination_is_not_truncated() -> None:
    assert rules.find_route("shipping from Delhi to Navi Mumbai Airport") is None
    assert rules.find_route("from Pune to Mumbai") == ("Pune", "Mumbai")


def test_an_unstorable_route_still_blocks_the_city_rule() -> None:
    """Refusing the route must not hand the shipping origin to `city` — that
    is the misread the route rule exists to prevent, arriving by a new door."""
    assert "city" not in _facts("shipping from Delhi to Navi Mumbai Airport")


def test_a_valid_update_is_untouched_by_the_guard() -> None:
    state, handle = initial_state(_state("Deadline is 15 August"))
    merged, _ = evolve_state(state, _state("Deadline is 20 September", state), handle)
    assert merged["constraints"]["deadline"]["iso"].endswith("-09-20")
    assert not (merged.get("_unmapped") or {})
