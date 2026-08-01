"""Structured conversational-state extraction for StateJar.

Extraction is a two-stage pipeline:

  1. a deterministic rule engine (regex + keyword patterns), and
  2. a GLiNER neural pass that catches everything the patterns missed.

Stage 2 is a standard part of the pipeline, not an add-on: it runs whenever
the model can be loaded (EXTRACTOR_MODE=auto, the default). It broadens
coverage — names, organizations, locations, contact details, amounts, dates,
requirements, products, decisions, goals — so a fact stated in a phrasing no
regex anticipated still reaches the state.

Rules win every conflict. Stage 2 only ever writes to a field stage 1 left
empty, because extraction feeds canonicalization: whatever wins here decides
the handle, and the rule engine is the deterministic half.

Deployment:
  * gliner/torch live in requirements-ml.txt, never requirements.txt, so the
    Railway build stays small. Where the extras are absent the pipeline
    silently runs stage 1 alone.
  * Import and model load are both deferred to first use, so startup never
    blocks and a deployment without the extras pays nothing.
  * Any failure (missing package, download error, bad prediction) logs once
    and falls back to the rule result.
  * EXTRACTOR_MODE=rules forces stage 1 alone — the escape hatch when you
    need extraction to be reproducible across machines.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)

# --- optional GLiNER layer ----------------------------------------------------

# Values reported as `extraction_source`. They are metadata only and never
# enter the canonicalized state, so they cannot affect a handle.
SOURCE_RULES = "rules"
SOURCE_GLINER = "gliner+rules"

GLINER_MODEL_NAME = "urchade/gliner_multi-v2.1"

# EXTRACTOR_MODE values. "auto" and "gliner" both run the neural stage and
# degrade to rules when it is unavailable; "rules" forces it off. Anything
# unrecognised is treated as "rules" — a typo must never silently put a
# neural model on the write path.
MODE_AUTO = "auto"
MODE_GLINER = "gliner"
MODE_RULES = "rules"
_NEURAL_MODES = {MODE_AUTO, MODE_GLINER}

# Entity label -> where it lands in StructuredState. GLiNER is zero-shot, so
# these label strings *are* the prompt: widening this table is how the
# pipeline learns to keep a new kind of fact. Money and contact preference
# need parsing, so they are handled explicitly in the merge below.
GLINER_TARGETS: dict[str, tuple[str, str]] = {
    "person name": ("facts", "name"),
    "organization or company": ("facts", "organization"),
    "city or location": ("facts", "city"),
    "email address": ("facts", "email"),
    "phone number": ("facts", "phone"),
    "date or deadline": ("constraints", "deadline"),
    "decision": ("decisions", "choice"),
    "product or item": ("decisions", "item"),
    "goal or objective": ("goals", "primary"),
}

# Labels that accumulate instead of replacing. The list is kept sorted so the
# canonical bytes never depend on the order GLiNER happened to emit spans in
# (the canonicalizer preserves list order, it does not sort for us).
GLINER_LIST_TARGETS: dict[str, tuple[str, str]] = {
    "requirement or specification": ("constraints", "requirements"),
}

GLINER_LABELS = [
    *GLINER_TARGETS,
    *GLINER_LIST_TARGETS,
    "money amount",
    "contact preference",
]

# Loaded at most once per process — a failed attempt is never retried, so a
# missing package costs one log line rather than an import storm.
_gliner_state: dict[str, Any] = {"attempted": False, "model": None}


def _gliner_enabled() -> bool:
    return get_settings().extractor_mode.strip().lower() in _NEURAL_MODES


def _load_gliner_model() -> Any | None:
    """Import and load the GLiNER model once. Returns None on any failure."""
    if _gliner_state["attempted"]:
        return _gliner_state["model"]
    _gliner_state["attempted"] = True
    try:  # pragma: no cover - requires the optional ML extras
        from gliner import GLiNER  # imported here: torch is slow to import

        _gliner_state["model"] = GLiNER.from_pretrained(GLINER_MODEL_NAME)
        logger.info("GLiNER extraction layer loaded (%s)", GLINER_MODEL_NAME)
    except Exception as exc:  # noqa: BLE001 — missing extras must never crash
        logger.warning(
            "GLiNER unavailable (%s: %s) — falling back to rule-based extraction. "
            "Install backend/requirements-ml.txt to enable it.",
            exc.__class__.__name__,
            exc,
        )
        _gliner_state["model"] = None
    return _gliner_state["model"]


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


# --- GLiNER merge -------------------------------------------------------------

# "40k" / "2,000" / "₹1.5 lakh"
_MONEY_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k|lakh|lakhs|cr|crore)?", re.IGNORECASE)
_MONEY_SCALE = {"k": 1_000, "lakh": 100_000, "lakhs": 100_000, "cr": 10_000_000, "crore": 10_000_000}


def _parse_money(value: str) -> int | None:
    """Best-effort amount from a money span; None when nothing parses."""
    m = _MONEY_RE.search(value)
    if not m:
        return None
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    amount *= _MONEY_SCALE.get((m.group(2) or "").lower(), 1)
    return int(amount) if amount > 0 else None


def _contact_mode_from(phrase: str) -> str | None:
    """Map a free-text preference span onto a known contact mode."""
    for mode, pat in _CONTACT_MODES.items():
        if pat.search(phrase) and not _is_negated(phrase, mode):
            return mode
    return None


def _predict_entities(model: Any, text: str) -> list[dict[str, Any]]:
    """Call whichever prediction API this model object exposes."""
    if hasattr(model, "predict_entities"):
        raw = model.predict_entities(text, GLINER_LABELS)
    else:  # gliner2-style API
        raw = model.extract_entities(text, GLINER_LABELS)
    if isinstance(raw, dict):
        raw = raw.get("entities", [])
    return [e for e in (raw or []) if isinstance(e, dict)]


def _merge_gliner(text: str, state: StructuredState) -> bool:
    """Fill gaps in `state` from GLiNER spans, in place.

    Rule-extracted values always win: every write below is conditional on the
    field being absent. Returns True when the model actually ran.
    """
    model = _load_gliner_model()
    if model is None:
        return False
    try:
        entities = _predict_entities(model, text)
    except Exception as exc:  # noqa: BLE001 — a bad prediction must not 500
        logger.warning("GLiNER prediction failed (%s) — using rules only", exc)
        return False

    sections: dict[str, dict[str, Any]] = {
        "facts": state.facts,
        "preferences": state.preferences,
        "decisions": state.decisions,
        "constraints": state.constraints,
        "goals": state.goals,
    }
    touched_lists: set[tuple[str, str]] = set()

    for ent in entities:
        label = str(ent.get("label", "")).strip().lower()
        value = str(ent.get("text", "")).strip()
        if not value:
            continue

        if label == "money amount":
            # skip entirely if the rules already found any budget figure —
            # adding the other key would fabricate a second, conflicting one
            if "budget_inr" not in state.constraints and "budget_inr_max" not in state.constraints:
                amount = _parse_money(value)
                if amount is not None:
                    key = (
                        "budget_inr_max"
                        if _BUDGET_MAX_QUAL_RE.search(text)
                        else "budget_inr"
                    )
                    state.constraints[key] = amount

        elif label == "contact preference":
            if "contact_mode" not in state.preferences and not state.conflicts:
                if mode := _contact_mode_from(value):
                    state.preferences["contact_mode"] = mode

        elif target := GLINER_TARGETS.get(label):
            section, field = target
            sections[section].setdefault(field, value)

        elif target := GLINER_LIST_TARGETS.get(label):
            section, field = target
            bucket = sections[section].setdefault(field, [])
            if isinstance(bucket, list):  # a rule scalar here wins outright
                if value not in bucket:
                    bucket.append(value)
                touched_lists.add((section, field))

    # sorted, so identical text yields identical canonical bytes no matter
    # what order the model emitted the spans in
    for section, field in touched_lists:
        sections[section][field] = sorted(sections[section][field])

    return True


# --- public API ---------------------------------------------------------------


def extract_state_with_source(text: str) -> tuple[StructuredState, str]:
    """Extract state plus the layer that produced it.

    The source is metadata for the UI only — it is deliberately *not* part of
    StructuredState, so canonicalization and therefore the handle are
    identical whichever extractor ran.
    """
    state = _extract_rules(text)
    if _gliner_enabled() and _merge_gliner(text, state):
        return state, SOURCE_GLINER
    return state, SOURCE_RULES


def extract_state(text: str) -> StructuredState:
    """Extract a StructuredState from raw user text."""
    return extract_state_with_source(text)[0]
