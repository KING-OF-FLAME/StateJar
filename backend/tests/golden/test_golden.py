"""Runs the golden corpus. This is the BUG-6 regression: extraction must work
on messages from domains StateJar was never tuned on.

Tier 1 only — no ML extras, no network, no provider key. That is deliberate:
it is the configuration the demo and the free tier actually run in, so a
message that needs tier 3 to extract anything at all is a rule-tier gap, not
a pass.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

from app.config import get_settings
from app.memory.extractor import extract_state
from app.memory.versioning import initial_state
from app.schema import canonical as canon
from app.schema import dynamic as dyn
from tests.golden.corpus import GOLDEN


@pytest.fixture(autouse=True)
def _rules_only(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("EXTRACTOR_MODE", "rules")
    monkeypatch.setenv("EXTRACTOR_LLM_FALLBACK", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _flat(state: dict[str, Any]) -> dict[str, Any]:
    """Canonical path -> comparable primitive."""
    out: dict[str, Any] = {}
    for section in canon.ACTIVE_SECTIONS:
        for path in canon.leaf_paths_in(state.get(section), section):
            value = canon.read_path(state, path)
            if isinstance(value, dict):
                value = value.get("value", value.get("iso", value))
            out[path] = value
    return out


@pytest.mark.parametrize("name,text,must,must_not",
                         GOLDEN, ids=[g[0] for g in GOLDEN])
def test_golden_case(name: str, text: str, must: dict, must_not: list) -> None:
    got = _flat(extract_state(text).model_dump())

    for path, expected in must.items():
        assert path in got, f"{name}: missing {path} (got {sorted(got)})"
        actual = got[path]
        if isinstance(expected, str) and expected.startswith("-"):
            # a date asserted on month-day only, because the year is inferred
            # from today and the corpus must not expire
            assert str(actual).endswith(expected), f"{name}: {path}={actual}"
        else:
            assert actual == expected, f"{name}: {path}={actual!r}"

    for path in must_not:
        assert path not in got, f"{name}: {path} should not be set ({got[path]!r})"


@pytest.mark.parametrize("name,text,must,must_not",
                         GOLDEN, ids=[g[0] for g in GOLDEN])
def test_golden_case_holds_the_invariant(
    name: str, text: str, must: dict, must_not: list
) -> None:
    """No canonical path may appear twice, for every message in the corpus."""
    state, _ = initial_state(extract_state(text).model_dump())
    canon.assert_no_duplicate_paths(state)


@pytest.mark.parametrize("name,text,must,must_not",
                         GOLDEN, ids=[g[0] for g in GOLDEN])
def test_golden_case_is_deterministic(
    name: str, text: str, must: dict, must_not: list
) -> None:
    """Same message, same handle — the property the patent claim rests on."""
    first, h1 = initial_state(extract_state(text).model_dump())
    second, h2 = initial_state(extract_state(text).model_dump())
    assert h1 == h2, name
    assert first == second, name


def test_every_live_path_is_registered_or_dynamic() -> None:
    """A live path is either a declared field or an explicit dynamic concept.

    It used to have to be a registry field, which is exactly why anything
    unfamiliar was dropped. The rule now is narrower and more useful: nothing
    lands in a *named* section that the registry does not know, and everything
    else is under `dynamic.` where its origin is visible.
    """
    for name, text, _must, _must_not in GOLDEN:
        state = extract_state(text).model_dump()
        for path in _flat(state):
            if path.startswith(f"{dyn.SECTION}."):
                continue
            assert canon.resolve(path) is not None, f"{name}: {path} is unregistered"


# Ordinary conversation. Generalising extraction is only worth anything if it
# stays silent here: a wrong fact is not a smaller version of a right one, it
# persists in state and is re-sent to the model on every later turn. Each of
# these produced a field at some point while the alias matcher was too loose —
# "the area is nice" set area="nice", "what's the name of that place?" named
# the user "That Place".
CHITCHAT = [
    "the area is nice and quiet",
    "what's the name of that place?",
    "I play a role in the team",
    "can you translate this language for me",
    "the city was crowded yesterday",
    "thanks, that works",
    "no",
    "please explain how handles work",
    "what did I tell you earlier?",
    "the plan is unclear",
    "count me in",
    "how much does it cost?",
    "the due date passed",
    "give me a number",
    "that item is broken",
    "hi hello there",
    "can you do that thing for me before then",
    "tell me a joke",
    "sounds good to me",
    "could you try again please",
]


@pytest.mark.parametrize("text", CHITCHAT)
def test_conversation_does_not_become_state(text: str) -> None:
    got = _flat(extract_state(text).model_dump())
    assert got == {}, f"{text!r} extracted {got}"


def test_corpus_covers_the_declared_domains() -> None:
    """A shrinking corpus is how BUG-6 came back last time."""
    assert len(GOLDEN) >= 40
    prefixes = {name.split("_", 1)[0] for name, *_ in GOLDEN}
    assert {"ecom", "travel", "health", "job", "food", "estate", "webdev",
            "messy"} <= prefixes
