"""Structured conversational-state extraction for StateJar.

Primary path is deterministic rule-based extraction (regex + keyword
patterns). If the optional GLiNER2 package is importable, its entity
predictions are merged in as a secondary signal; any GLiNER2 failure
falls back silently to the rule-based result.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

# --- optional GLiNER2 support -------------------------------------------------

try:  # pragma: no cover - depends on environment
    from gliner2 import GLiNER2  # type: ignore

    _GLINER_AVAILABLE = True
except Exception:  # ImportError or any transitive failure
    GLiNER2 = None  # type: ignore
    _GLINER_AVAILABLE = False

_gliner_model: Any | None = None


def _get_gliner_model() -> Any | None:
    """Lazily load the GLiNER2 model; return None on any failure."""
    global _gliner_model
    if not _GLINER_AVAILABLE:
        return None
    if _gliner_model is None:
        try:  # pragma: no cover - depends on environment
            _gliner_model = GLiNER2.from_pretrained("fastino/gliner2-base")
        except Exception:
            return None
    return _gliner_model


# --- output schema ------------------------------------------------------------


class UnresolvedField(BaseModel):
    field: str
    reason: str


class StructuredState(BaseModel):
    facts: dict[str, Any] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    decisions: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    goals: dict[str, Any] = Field(default_factory=dict)
    unresolved: list[UnresolvedField] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


# --- rule-based patterns ------------------------------------------------------

_NAME_RE = re.compile(
    r"\b(?:my name is|i am called|call me|this is)\s+([A-Z][a-zA-Z]+)", re.IGNORECASE
)

# ₹2000 / Rs 2,000 / INR 2000, with an optional under/max/below/upto qualifier before
_BUDGET_RE = re.compile(
    r"(?P<qual>under|below|max(?:imum)?|up\s*to|at most|within)?\s*"
    r"(?:₹|rs\.?|inr)\s*(?P<amount>\d[\d,]*)",
    re.IGNORECASE,
)
_BUDGET_MAX_QUAL_RE = re.compile(r"\b(under|below|max(?:imum)?|up\s*to|at most|within|only)\b", re.IGNORECASE)

_CONTACT_MODES = {
    "email": re.compile(r"\be-?mails?\b", re.IGNORECASE),
    "call": re.compile(r"\b(?:calls?|phone)\b", re.IGNORECASE),
    "whatsapp": re.compile(r"\bwhats\s?app\b", re.IGNORECASE),
}
_PREFER_RE = re.compile(r"\bprefer(?:red|s)?\b|\bcontact me (?:via|by|on)\b", re.IGNORECASE)
_NEGATED_TEMPLATE = r"\b(?:not?|never|avoid|don'?t|no)\b[^.;]*?\b{word}s?\b"

_DECISION_RE = re.compile(
    r"\b(?:i(?:'ll| will)? go with|i(?:'ve| have)? decided (?:on|to go with)|"
    r"let'?s go with|i(?:'ll| will) take|final(?:ized)? (?:choice|decision)(?: is)?)\s+"
    r"(?:the\s+)?([A-Za-z0-9][\w -]*?)(?=[.,;!]|$)",
    re.IGNORECASE,
)

_DEADLINE_RE = re.compile(
    r"\b(?:deadline is|due (?:by|on)|by|before)\s+"
    r"((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|"
    r"next week|end of (?:the )?(?:day|week|month)|"
    r"\d{1,2}(?:st|nd|rd|th)?\s+\w+|\w+\s+\d{1,2}(?:st|nd|rd|th)?))",
    re.IGNORECASE,
)

_GOAL_RE = re.compile(
    r"\b(?:i want to|my goal is to|i(?:'m| am) (?:trying|looking) to|i need to)\s+"
    r"([^.,;!]+)",
    re.IGNORECASE,
)

_UNRESOLVED_RE = re.compile(
    r"\b(?:i )?(?:haven'?t|have not|didn'?t|not yet|still haven'?t)\s+"
    r"(?:decided|chosen|picked|figured out|finalized)\s+(?:on\s+)?(?:the\s+|a\s+|my\s+)?"
    r"([^.,;!]+)",
    re.IGNORECASE,
)
_UNSURE_RE = re.compile(
    r"\b(?:not sure|unsure|undecided) (?:about|on)\s+(?:the\s+|my\s+)?([^.,;!]+)",
    re.IGNORECASE,
)


def _slug(text: str) -> str:
    """Normalize a phrase into a snake_case field name."""
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def _is_negated(text: str, word: str) -> bool:
    return bool(re.search(_NEGATED_TEMPLATE.format(word=word), text, re.IGNORECASE))


# --- rule-based extraction ----------------------------------------------------


def _extract_rules(text: str) -> StructuredState:
    state = StructuredState()

    # facts: name
    if m := _NAME_RE.search(text):
        state.facts["name"] = m.group(1)

    # constraints: budget
    if m := _BUDGET_RE.search(text):
        amount = int(m.group("amount").replace(",", ""))
        # qualifier may sit before the currency token or earlier in the clause
        clause_start = max(text.rfind(".", 0, m.start()), text.rfind(",", 0, m.start())) + 1
        clause = text[clause_start : m.end()]
        if m.group("qual") or _BUDGET_MAX_QUAL_RE.search(clause):
            state.constraints["budget_inr_max"] = amount
        else:
            state.constraints["budget_inr"] = amount

    # preferences: contact mode
    if _PREFER_RE.search(text):
        chosen = [
            mode
            for mode, pat in _CONTACT_MODES.items()
            if pat.search(text) and not _is_negated(text, mode)
        ]
        if len(chosen) == 1:
            state.preferences["contact_mode"] = chosen[0]
        elif len(chosen) > 1:
            state.conflicts.append(
                {"field": "contact_mode", "values": chosen, "reason": "multiple preferred modes"}
            )

    # decisions
    if m := _DECISION_RE.search(text):
        state.decisions["choice"] = m.group(1).strip()

    # constraints: deadline
    if m := _DEADLINE_RE.search(text):
        state.constraints["deadline"] = m.group(1).strip()

    # goals
    if m := _GOAL_RE.search(text):
        state.goals["primary"] = m.group(1).strip()

    # unresolved
    for pat, reason in ((_UNRESOLVED_RE, "not provided"), (_UNSURE_RE, "user unsure")):
        for m in pat.finditer(text):
            field = _slug(m.group(1))
            if field and not any(u.field == field for u in state.unresolved):
                state.unresolved.append(UnresolvedField(field=field, reason=reason))

    return state


# --- GLiNER2 merge ------------------------------------------------------------

_GLINER_LABELS = ["person", "money", "date", "product"]


def _merge_gliner(text: str, state: StructuredState) -> StructuredState:
    """Merge GLiNER2 entity predictions into a rule-based state. Never raises."""
    model = _get_gliner_model()
    if model is None:
        return state
    try:  # pragma: no cover - depends on environment
        entities = model.extract_entities(text, _GLINER_LABELS)
        for ent in entities.get("entities", []) if isinstance(entities, dict) else entities:
            label = str(ent.get("label", "")).lower()
            value = str(ent.get("text", "")).strip()
            if not value:
                continue
            if label == "person":
                state.facts.setdefault("name", value)
            elif label == "date":
                state.constraints.setdefault("deadline", value)
            elif label == "product":
                state.facts.setdefault("product", value)
    except Exception:
        pass
    return state


# --- public API ---------------------------------------------------------------


def extract_state(text: str) -> StructuredState:
    """Extract a StructuredState from raw user text.

    Rule-based extraction always runs; GLiNER2 results are merged in only
    when the package is available and functional.
    """
    state = _extract_rules(text)
    return _merge_gliner(text, state)
