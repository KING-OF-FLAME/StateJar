"""Structured conversational-state extraction for StateJar.

Three tiers, cheapest and most deterministic first:

  1. rules   — regex over clauses (app/memory/rules.py). Always runs.
  2. gliner2 — schema-guided neural extraction, EXTRACTOR_MODE=gliner.
  3. llm     — strict-JSON extraction through the user's own provider key,
               EXTRACTOR_LLM_FALLBACK=true, and only for the messy case.

WHY PROBABILISTIC TIERS ARE SAFE HERE
-------------------------------------
Extraction runs strictly BEFORE canonicalization. A tier's only power is to
propose field values; the canonicalizer then sorts, normalises and serialises
whatever it is given, and the handle is a SHA-256 of those bytes. So identity
is a function of the *extracted fields*, never of which tier proposed them —
two states with the same fields hash identically whether a regex, a neural
model, or an LLM produced them. `extraction_source` is reported as metadata
outside `state` for exactly this reason: it must never reach the canonical
bytes. test_extractor_hard.py asserts both properties.

Tier ordering is also the conflict-resolution order: rules win, because they
are the only tier that returns the same answer on every machine. The neural
tiers may only fill fields the rules left empty.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field as dc_field
from typing import Any

from pydantic import BaseModel, Field

from app.config import get_settings
from app.memory import rules

logger = logging.getLogger(__name__)

SOURCE_RULES = "rules"
SOURCE_GLINER = "gliner2"
SOURCE_LLM = "llm"

GLINER_MODEL_NAME = "urchade/gliner_multi-v2.1"
GLINER_MIN_CONFIDENCE = 0.5

# Tier 3 only earns its cost on genuinely messy input.
LLM_MIN_WORDS = 12
LLM_MAX_FIELDS = 2
LLM_TIMEOUT_S = 8.0

MODE_AUTO = "auto"
MODE_GLINER = "gliner"
MODE_RULES = "rules"
_NEURAL_MODES = {MODE_AUTO, MODE_GLINER}


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


@dataclass
class Extraction:
    """The state plus who produced what — metadata only, never canonicalized."""

    state: StructuredState
    sources: list[str] = dc_field(default_factory=lambda: [SOURCE_RULES])
    origins: dict[str, str] = dc_field(default_factory=dict)


_SECTIONS = ("facts", "preferences", "decisions", "constraints", "goals")


def _section(state: StructuredState, name: str) -> dict[str, Any]:
    return getattr(state, name)


def _put(
    state: StructuredState, origins: dict[str, str], source: str,
    section: str, key: str, value: Any,
) -> bool:
    """Write a field only if it is still empty. Returns True if it landed."""
    target = _section(state, section)
    if key in target or value in (None, "", [], {}):
        return False
    target[key] = value
    origins[f"{section}.{key}"] = source
    return True


def field_count(state: StructuredState) -> int:
    return sum(len(_section(state, s)) for s in _SECTIONS) + len(state.unresolved)


# --- tier 1: rules ------------------------------------------------------------


def extract_rules(text: str) -> tuple[StructuredState, dict[str, str]]:
    """Deterministic pass. Every pattern runs on every clause."""
    state = StructuredState()
    origins: dict[str, str] = {}
    seen_dates: list[str] = []
    rejected_modes: list[str] = []

    # Build-spec values are sentence-scoped and their own patterns already
    # stop at a clause end, so they run once over the whole utterance. Per
    # clause, "stack is Next.js and Postgres" would truncate at the "and", and
    # "No external UI libraries. Use shadcn/ui" would let the earlier blanket
    # ban win over the later, more specific instruction.
    for section, key, value in rules.find_build_spec(text):
        _put(state, origins, SOURCE_RULES, section, key, value)

    for clause in rules.split_clauses(text):
        if name := rules.find_name(clause):
            _put(state, origins, SOURCE_RULES, "facts", "name", name)

        if city := rules.find_city(clause):
            _put(state, origins, SOURCE_RULES, "facts", "city", city)

        if money := rules.find_money(clause):
            amount, is_ceiling = money
            key = "budget_inr_max" if is_ceiling else "budget_inr"
            # a ceiling and a plain amount are different facts; neither
            # overwrites the other, and the first one stated wins its key
            if "budget_inr" not in state.constraints and "budget_inr_max" not in state.constraints:
                _put(state, origins, SOURCE_RULES, "constraints", key, amount)

        mode, rejected = rules.find_contact(clause)
        for r in rejected:
            if r not in rejected_modes:
                rejected_modes.append(r)
        if mode:
            _put(state, origins, SOURCE_RULES, "preferences", "contact_mode", mode)

        for value in rules.find_dates(clause):
            if value not in seen_dates:
                seen_dates.append(value)

        if decision := rules.find_decision(clause):
            _put(state, origins, SOURCE_RULES, "decisions", "choice", decision)

        if m := rules._REQUIREMENT.search(clause):
            requirement = m.group(1).strip()
            if requirement:
                existing = state.constraints.get("requirements")
                if existing is None:
                    _put(state, origins, SOURCE_RULES, "constraints",
                         "requirements", [requirement])
                elif isinstance(existing, list) and requirement not in existing:
                    existing.append(requirement)
                    state.constraints["requirements"] = sorted(existing)

        if m := rules._GOAL.search(clause):
            _put(state, origins, SOURCE_RULES, "goals", "primary", m.group(1).strip())

        for field_name, reason in rules.find_unresolved(clause):
            if not any(u.field == field_name for u in state.unresolved):
                state.unresolved.append(UnresolvedField(field=field_name, reason=reason))
                origins[f"unresolved.{field_name}"] = SOURCE_RULES

    if seen_dates:
        _put(state, origins, SOURCE_RULES, "constraints", "deadline", seen_dates[0])
        if len(seen_dates) > 1:
            _put(state, origins, SOURCE_RULES, "constraints",
                 "additional_dates", sorted(seen_dates[1:]))

    # an explicit switch ("call me instead of email") is a contradiction worth
    # recording, not just a preference update
    chosen = state.preferences.get("contact_mode")
    for rejected in rejected_modes:
        if chosen and rejected != chosen:
            state.conflicts.append({
                "field": "contact_mode",
                "values": [chosen, rejected],
                "reason": f"user rejected {rejected} in favour of {chosen}",
            })
            break

    return state, origins


# --- tier 2: GLiNER2 ----------------------------------------------------------

# label -> (section, key). The schema StateJar actually stores, so the model
# is asked for the fields we keep rather than generic entity types.
GLINER_SCHEMA: dict[str, tuple[str, str]] = {
    "person name": ("facts", "name"),
    "city": ("facts", "city"),
    "monetary amount": ("constraints", "budget_inr"),
    "budget ceiling": ("constraints", "budget_inr_max"),
    "contact preference": ("preferences", "contact_mode"),
    "decision": ("decisions", "choice"),
    "constraint": ("constraints", "requirement"),
    "goal": ("goals", "primary"),
    "deadline": ("constraints", "deadline"),
    "unresolved item": ("unresolved", "item"),
}
GLINER_LABELS = list(GLINER_SCHEMA)

_gliner_state: dict[str, Any] = {"attempted": False, "model": None}


def _gliner_enabled() -> bool:
    return get_settings().extractor_mode.strip().lower() in _NEURAL_MODES


def _load_gliner_model() -> Any | None:
    """Import and load once. Any failure is permanent and silent after one log."""
    if _gliner_state["attempted"]:
        return _gliner_state["model"]
    _gliner_state["attempted"] = True
    try:  # pragma: no cover - requires the optional ML extras
        from gliner import GLiNER  # imported here: torch is slow to import

        _gliner_state["model"] = GLiNER.from_pretrained(GLINER_MODEL_NAME)
        logger.info("GLiNER2 extraction tier loaded (%s)", GLINER_MODEL_NAME)
    except Exception as exc:  # noqa: BLE001 — missing extras must never crash
        logger.warning(
            "GLiNER2 unavailable (%s: %s) — continuing with rules only. "
            "Install backend/requirements-ml.txt to enable it.",
            exc.__class__.__name__, exc,
        )
        _gliner_state["model"] = None
    return _gliner_state["model"]


def _predict(model: Any, text: str) -> list[dict[str, Any]]:
    """Whichever schema/NER interface this build of GLiNER exposes."""
    if hasattr(model, "extract"):          # GLiNER2 schema interface
        raw = model.extract(text, GLINER_SCHEMA_SPEC)
    elif hasattr(model, "predict_entities"):
        raw = model.predict_entities(text, GLINER_LABELS)
    else:
        raw = model.extract_entities(text, GLINER_LABELS)
    if isinstance(raw, dict):
        raw = raw.get("entities", [])
    return [e for e in (raw or []) if isinstance(e, dict)]


# GLiNER2 takes a schema description rather than a flat label list.
GLINER_SCHEMA_SPEC = {"entities": GLINER_LABELS}


def merge_gliner(
    text: str, state: StructuredState, origins: dict[str, str]
) -> bool:
    """Fill gaps from GLiNER2. Returns True only if the model actually ran."""
    model = _load_gliner_model()
    if model is None:
        return False
    try:
        entities = _predict(model, text)
    except Exception as exc:  # noqa: BLE001 — a bad prediction must not 500
        logger.warning("GLiNER2 prediction failed (%s) — using rules only", exc)
        return False

    for ent in entities:
        label = str(ent.get("label", "")).strip().lower()
        value = str(ent.get("text", "")).strip()
        score = ent.get("score", ent.get("confidence", 1.0))
        if not value or label not in GLINER_SCHEMA:
            continue
        try:
            if float(score) < GLINER_MIN_CONFIDENCE:
                continue
        except (TypeError, ValueError):
            pass

        section, key = GLINER_SCHEMA[label]

        if section == "unresolved":
            slug = rules.slugify(value)
            if slug and not any(u.field == slug for u in state.unresolved):
                state.unresolved.append(UnresolvedField(field=slug, reason="not provided"))
                origins[f"unresolved.{slug}"] = SOURCE_GLINER
            continue

        if key == "name":
            # the same blocklist the rules use — a neural span is no more
            # entitled to name someone "via" than a regex was
            if value.lower() in rules.NAME_STOPWORDS:
                continue
            value = value.title()
        elif key == "city":
            if value.lower() in rules.NAME_STOPWORDS:
                continue
            value = value.title()
        elif key in ("budget_inr", "budget_inr_max"):
            parsed = rules.find_money(value)
            if parsed is None:
                continue
            if "budget_inr" in state.constraints or "budget_inr_max" in state.constraints:
                continue
            value = parsed[0]
        elif key == "contact_mode":
            mode, _ = rules.find_contact(f"prefer {value}")
            if mode is None:
                continue
            value = mode
        elif key == "requirement":
            existing = state.constraints.get("requirements")
            if isinstance(existing, list):
                if value not in existing:
                    state.constraints["requirements"] = sorted([*existing, value])
                continue
            key = "requirements"
            value = [value]

        _put(state, origins, SOURCE_GLINER, section, key, value)

    return True


# --- tier 3: LLM structured extraction ----------------------------------------

_LLM_PROMPT = (
    "You extract structured state from a user message. Reply with STRICT JSON "
    "only — no prose, no markdown fence. Use exactly this shape, omitting any "
    "key you cannot fill:\n"
    '{"facts":{"name":"","city":""},"preferences":{"contact_mode":"email|call|whatsapp|sms"},'
    '"decisions":{"choice":""},"constraints":{"budget_inr":0,"budget_inr_max":0,"deadline":""},'
    '"goals":{"primary":""},"unresolved":[{"field":"","reason":""}]}\n'
    "budget_inr is a plain amount; budget_inr_max is a stated ceiling. "
    "Never invent a value that is not in the message."
)


def _llm_should_run(text: str, state: StructuredState) -> bool:
    if not get_settings().extractor_llm_fallback:
        return False
    return len(text.split()) > LLM_MIN_WORDS and field_count(state) < LLM_MAX_FIELDS


def merge_llm(
    text: str, state: StructuredState, origins: dict[str, str],
    db: Any = None, user_id: int | None = None,
) -> bool:
    """Last resort for messy input. Never raises, never retries."""
    if db is None or user_id is None:
        return False
    try:
        from app.llm.gateway import chat as gateway_chat

        result = gateway_chat(
            db, user_id,
            model=get_settings().extractor_llm_model,
            system_context=_LLM_PROMPT,
            user_message=text,
        )
        payload = _parse_json(result.get("text") or result.get("content") or "")
    except Exception as exc:  # noqa: BLE001 — no key, no credit, bad JSON: all fine
        logger.info("LLM extraction tier skipped (%s)", exc.__class__.__name__)
        return False
    if not payload:
        return False

    landed = False
    for section in _SECTIONS:
        values = payload.get(section)
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if key == "name" and str(value).lower() in rules.NAME_STOPWORDS:
                continue
            if key in ("budget_inr", "budget_inr_max"):
                if "budget_inr" in state.constraints or "budget_inr_max" in state.constraints:
                    continue
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
                if value <= 0:
                    continue
            landed |= _put(state, origins, SOURCE_LLM, section, key, value)

    for item in payload.get("unresolved") or []:
        if not isinstance(item, dict):
            continue
        slug = rules.slugify(str(item.get("field", "")))
        if slug and not any(u.field == slug for u in state.unresolved):
            state.unresolved.append(
                UnresolvedField(field=slug, reason=str(item.get("reason") or "not provided"))
            )
            origins[f"unresolved.{slug}"] = SOURCE_LLM
            landed = True
    return landed


def _parse_json(text: str) -> dict[str, Any] | None:
    """Tolerate a fenced or prose-wrapped JSON object."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?|```$", "", candidate, flags=re.MULTILINE).strip()
    if not candidate.startswith("{"):
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if not match:
            return None
        candidate = match.group(0)
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


# --- public API ---------------------------------------------------------------


def extract(text: str, db: Any = None, user_id: int | None = None) -> Extraction:
    """Run the tiers in order and report which ones contributed."""
    state, origins = extract_rules(text)
    sources = [SOURCE_RULES]

    if _gliner_enabled() and merge_gliner(text, state, origins):
        sources.append(SOURCE_GLINER)

    if _llm_should_run(text, state) and merge_llm(text, state, origins, db, user_id):
        sources.append(SOURCE_LLM)

    return Extraction(state=state, sources=sources, origins=origins)


def extract_state_with_source(
    text: str, db: Any = None, user_id: int | None = None
) -> tuple[StructuredState, list[str]]:
    """Back-compatible shim; `sources` is a list now, not a single string."""
    result = extract(text, db, user_id)
    return result.state, result.sources


def extract_state(text: str) -> StructuredState:
    """Extract a StructuredState from raw user text."""
    return extract(text).state


# kept so existing imports and tests keep resolving
_extract_rules = lambda text: extract_rules(text)[0]  # noqa: E731
_merge_gliner = lambda text, state: merge_gliner(text, state, {})  # noqa: E731
_parse_money = lambda value: (rules.find_money(value) or (None,))[0]  # noqa: E731
