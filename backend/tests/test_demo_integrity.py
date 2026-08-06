"""Every benchmark turn has to earn its place.

The saving is a ratio, so it can be inflated without touching the formula:
add turns that carry nothing and the denominator grows while the numerator
barely moves. That is the specific dishonesty this file exists to prevent, and
it has to be mechanical — "we checked" is not something a jury can audit.

A turn is legitimate when it either changes the state (a new field, a changed
value, a retraction, a decline) or asks something that needs memory to answer.
A turn that does neither is filler, and filler fails the build.
"""

from __future__ import annotations

import json

import pytest

from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.extractor import extract_state
from app.memory.handle import generate_handle
from app.memory.versioning import evolve_state
from app.schema import canonical as canon
from benchmarks.demos import DEMOS, RELIEF_40

QUESTION_STARTS = ("what", "how", "who", "when", "where", "which", "is ",
                   "are ", "do ", "does ", "remind", "summar", "tell me")


def _leaves(state: dict) -> set[str]:
    out: set[str] = set()
    for section in canon.ACTIVE_SECTIONS:
        out.update(canon.leaf_paths_in(state.get(section), section))
    return out


def _asks_something(msg: str) -> bool:
    lowered = msg.strip().lower()
    return lowered.endswith("?") or lowered.startswith(QUESTION_STARTS)


def _walk(turns):
    """Replay a demo, yielding what each turn actually did."""
    state = handle = None
    prev_leaves: set[str] = set()
    prev_history = prev_unresolved = prev_declines = 0

    for index, (_session, msg) in enumerate(turns, start=1):
        extracted = extract_state(msg).model_dump()
        if state is None:
            state = json.loads(canonicalize(extracted))
            handle = generate_handle(canonicalize(extracted), SCHEMA_VERSION, NORM_VERSION)
        else:
            state, handle = evolve_state(state, extracted, handle)
            state.pop("parent_handle", None)

        leaves = _leaves(state)
        history = len(state.get("history") or [])
        unresolved = len(state.get("unresolved") or [])
        declines = len(state.get("_unmapped") or {})

        yield {
            "turn": index,
            "message": msg,
            "added": leaves - prev_leaves,
            "removed": prev_leaves - leaves,
            "new_history": history - prev_history,
            "new_unresolved": unresolved - prev_unresolved,
            "new_declines": declines - prev_declines,
            "asks": _asks_something(msg),
            "state": state,
        }
        prev_leaves, prev_history = leaves, history
        prev_unresolved, prev_declines = unresolved, declines


@pytest.mark.parametrize("name", sorted(DEMOS))
def test_no_turn_is_filler(name: str) -> None:
    """The anti-padding rule, enforced rather than promised."""
    dead = [
        f"turn {t['turn']}: {t['message']!r}"
        for t in _walk(DEMOS[name])
        if not t["asks"]
        and not t["added"] and not t["removed"]
        and not t["new_history"] and not t["new_unresolved"] and not t["new_declines"]
    ]
    assert not dead, (
        f"{name}: these turns changed nothing and asked nothing, so they only "
        "make the denominator bigger:\n  " + "\n  ".join(dead)
    )


@pytest.mark.parametrize("name", sorted(DEMOS))
def test_no_question_turn_writes_junk_into_state(name: str) -> None:
    """A question is a read. One that also writes has been mis-extracted, and
    the field it invents is then disclosed on every later turn."""
    offenders = [
        f"turn {t['turn']}: {t['message']!r} wrote {sorted(t['added'])}"
        for t in _walk(DEMOS[name])
        if t["asks"] and t["added"]
    ]
    assert not offenders, "\n  ".join(offenders)


def test_the_long_demo_exercises_what_makes_the_product_different() -> None:
    """The differentiators are the reason the demo is worth watching. If one
    stops firing, the demo still runs and quietly proves less."""
    walked = list(_walk(RELIEF_40))
    final = walked[-1]["state"]

    multi_fact = [t for t in walked if len(t["added"]) >= 2]
    assert multi_fact, "no message landed two fields at once"

    assert any(t["new_history"] for t in walked), "no update moved a value to history"
    assert any(t["removed"] for t in walked), "no retraction removed a live field"
    assert final.get("unresolved"), "no field was declined with a stated reason"
    assert all(e.get("reason") for e in final["unresolved"]), \
        "a decline without a reason is just a missing field"


def test_the_long_demo_spans_sessions() -> None:
    """Cross-session recall is the claim; one session cannot demonstrate it."""
    sessions = [s for s, _ in RELIEF_40]
    assert len(set(sessions)) >= 3
    # and the sessions are contiguous blocks, not interleaved — a judge should
    # be able to see where one ends and the next begins
    assert sessions == sorted(sessions, key=lambda s: sessions.index(s))


def test_the_short_demo_matches_the_shipped_ui_demo() -> None:
    """`relief-17` is the conversation the UI actually plays. If they drift,
    the published figure stops describing what a viewer sees."""
    from pathlib import Path
    jsx = (Path(__file__).resolve().parents[2] / "frontend" / "src" /
           "components" / "ReliefDemo.jsx").read_text(encoding="utf-8")
    assert jsx.count("user:") == len(DEMOS["relief-17"]), (
        "ReliefDemo.jsx and benchmarks/demos.py no longer have the same "
        "number of turns"
    )
