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


# --- build-spec extraction (the demo's developer scenario) --------------------

BRIEF = (
    "Build me a landing page. Stack: React + Tailwind. Dark theme, "
    "brand color #E07856. No external UI libraries. "
    "Target audience: Indian SMB owners."
)


def test_build_brief_extracts_every_spec_field() -> None:
    state = extract_state(BRIEF)
    assert state.decisions["stack"] == "React + Tailwind"
    assert state.preferences["theme"] == "dark"
    assert state.preferences["brand_color"] == "#E07856"
    assert state.constraints["no_ui_libs"] == "none"
    assert state.facts["audience"] == "Indian SMB owners"


def test_hex_colour_case_is_normalized() -> None:
    """#e07856 and #E07856 are the same colour and must not mint two handles."""
    assert extract_state("brand color #e07856").preferences["brand_color"] == "#E07856"
    assert extract_state("brand color #E07856").preferences["brand_color"] == "#E07856"


def test_named_library_overrides_the_blanket_ban() -> None:
    """The later, specific instruction wins; the contradiction surfaces as a conflict."""
    assert extract_state("Use shadcn/ui for the components.").constraints[
        "no_ui_libs"] == "shadcn/ui"
    assert extract_state("No external UI libraries.").constraints["no_ui_libs"] == "none"
    # both present: the named library is what the user actually asked for
    both = extract_state("No external UI libraries. Use shadcn/ui for the components.")
    assert both.constraints["no_ui_libs"] == "shadcn/ui"


def test_theme_and_stack_phrasings() -> None:
    assert extract_state("theme: light").preferences["theme"] == "light"
    assert extract_state("tech stack is Next.js and Postgres").decisions[
        "stack"] == "Next.js and Postgres"


def test_build_brief_does_not_disturb_the_older_rules() -> None:
    """The new family must not fire on, or break, the original patterns."""
    old = extract_state("My name is Ayaan, budget under ₹2000. I prefer email.")
    assert old.facts == {"name": "Ayaan"}
    assert old.preferences == {"contact_mode": "email"}
    assert old.constraints == {"budget_inr_max": 2000}
    assert old.decisions == {}
