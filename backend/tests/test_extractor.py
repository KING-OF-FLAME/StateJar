"""Tests for the rule-based structured state extractor."""

from app.memory.extractor import StructuredState, extract_state


def test_example_from_spec() -> None:
    text = (
        "My name is Ayaan. I prefer emails, not calls. "
        "Budget is under ₹2000. I haven't decided the delivery time."
    )
    state = extract_state(text)
    assert state.facts["name"] == "Ayaan"
    assert state.preferences["contact_mode"] == "email"
    assert state.constraints["budget_inr_max"] == 2000
    assert any(
        u.field == "delivery_time" and u.reason == "not provided"
        for u in state.unresolved
    )


def test_decision_and_deadline() -> None:
    text = "I'll go with the blue variant. Deadline is Friday."
    state = extract_state(text)
    assert state.decisions["choice"] == "blue variant"
    assert state.constraints["deadline"].lower() == "friday"


def test_budget_rs_with_commas_and_goal() -> None:
    text = "I want to renovate my kitchen. Max Rs 1,50,000."
    state = extract_state(text)
    assert state.goals["primary"] == "renovate my kitchen"
    assert state.constraints["budget_inr_max"] == 150000


def test_whatsapp_preference_and_unsure() -> None:
    text = "I prefer WhatsApp for updates. I'm not sure about the paint color."
    state = extract_state(text)
    assert state.preferences["contact_mode"] == "whatsapp"
    assert any(
        u.field == "paint_color" and u.reason == "user unsure"
        for u in state.unresolved
    )


def test_empty_text_returns_empty_state() -> None:
    state = extract_state("The weather is nice today.")
    assert isinstance(state, StructuredState)
    assert state.facts == {}
    assert state.preferences == {}
    assert state.decisions == {}
    assert state.constraints == {}
    assert state.goals == {}
    assert state.unresolved == []
    assert state.conflicts == []
