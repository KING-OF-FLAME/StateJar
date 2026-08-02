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
from app.schema import canonical as canon

logger = logging.getLogger(__name__)

SOURCE_RULES = "rules"
SOURCE_GLINER = "gliner2"
SOURCE_LLM = "llm"

GLINER_MODEL_NAME = "urchade/gliner_multi-v2.1"
GLINER_MIN_CONFIDENCE = 0.5

# Tier 3 only earns its cost on genuinely messy input.
LLM_MIN_WORDS = 12
LLM_LONG_MESSAGE = 40
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
    # quarantine: keys no canonical path claims. Kept so the registry can be
    # grown from what real users actually said, never merged into active state.
    unmapped: dict[str, Any] = Field(default_factory=dict)


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
    section: str, key: str, value: Any, *, confidence: float | None = None,
) -> bool:
    """The one door into state. Returns True if the write landed.

    Nothing reaches a section except through here, and here everything goes
    through the canonical registry: the alias collapses to a single path and
    the raw value is normalized. That is what makes it impossible for
    `budget_inr` and `budget_inr_max` to coexist — they are the same path
    before the write happens, not two rows to reconcile afterwards.

    A key the registry does not know, or a value its normalizer rejects, is
    quarantined rather than stored. Losing an uncertain fact is recoverable;
    asserting a wrong one is not.
    """
    if value in (None, "", [], {}):
        return False

    raw_path = f"{section}.{key}"

    # Occupancy is checked before anything else. A later tier proposing a value
    # a rule already wrote is normal operation, not a rejection — quarantining
    # it would make the quarantine (and therefore the state) differ depending
    # on which tiers happened to run, and the whole point of tiering is that it
    # cannot change the handle.
    spec = canon.resolve(raw_path)
    if spec is not None:
        target = _section(state, spec.section)
        if canon.read_path(target, spec.path.split(".", 1)[1]) is not None:
            return False

    if confidence is None:
        confidence = canon.CONFIDENCE.get(source, 1.0)

    resolved = canon.canonicalize(
        raw_path, value, confidence=confidence, source=source
    )
    if resolved is None:
        _quarantine(state, raw_path, value, source, confidence)
        return False

    path, canonical_value = resolved
    canon.write_path(_section(state, path.split(".", 1)[0]), path.split(".", 1)[1],
                     canonical_value)
    origins[path] = source
    return True


def _quarantine(
    state: StructuredState, raw_key: str, value: Any, source: str,
    confidence: float = 1.0,
) -> None:
    """Park an unmappable write where it stays queryable for schema review.

    Three distinct reasons, kept apart because they call for different
    responses: an unknown key means the registry needs a new alias, a rejected
    value means the normalizer disagreed with the extractor, and low
    confidence means the tier itself was unsure.
    """
    spec = canon.resolve(raw_key)
    if spec is None:
        reason = "unknown_key"
    elif confidence < spec.required_confidence:
        reason = "low_confidence"
    else:
        reason = "rejected_value"
    state.unmapped[raw_key] = {"value": value, "reason": reason, "source": source}


def _section_for(raw_key: str) -> str:
    """Which section a bare key belongs to, per the registry.

    The generic assignment rule finds "bedrooms: 3" without knowing whether
    bedrooms is a fact or a constraint. Unknown keys are addressed to `facts`
    so `_put` can quarantine them under a stable name.
    """
    spec = canon.resolve(raw_key)
    return spec.section if spec else "facts"


# The registry's vocabulary, compiled once. Every alias of every field becomes
# matchable the moment it is registered — that is the whole point of deriving
# the pattern rather than writing one per field.
_ALIAS_MATCHER = rules.build_alias_matcher({
    alias: spec.path
    for spec in canon.REGISTRY
    for alias in (spec.leaf, *spec.aliases)
    # Two-letter aliases match inside other words too readily. Everyday
    # English words are kept, but the matcher restricts them to a declarative
    # form — see rules.GENERIC_ALIASES.
    if len(alias) >= 3
})

# Enum fields are the only ones a bare value can identify on its own: "prefer
# UPI" names no key, but only one field in the registry accepts "UPI".
_ENUM_SPECS = tuple(s for s in canon.REGISTRY if s.type == "enum")


def _put_enum_guess(
    state: StructuredState, origins: dict[str, str], value: str
) -> bool:
    """Route a keyless preference ("prefer whatsapp") by which enum accepts it.

    Only unambiguous values are taken: if two enums would both accept it, the
    sentence genuinely did not say which one was meant.
    """
    matches = [s for s in _ENUM_SPECS if s.normalizer(value) is not None]
    if len(matches) != 1:
        return False
    spec = matches[0]
    return _put(state, origins, SOURCE_RULES, spec.section, spec.leaf, value)


def field_count(state: StructuredState) -> int:
    """Live canonical fields. Quarantined keys are not facts, so they do not count."""
    return sum(
        len(list(canon.leaf_paths_in(_section(state, s), s))) for s in _SECTIONS
    ) + len(state.unresolved)


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

        # a route claims both endpoints before the city rule can read the
        # origin as a home town
        if route := rules.find_route(clause):
            _put(state, origins, SOURCE_RULES, "constraints", "origin", route[0])
            _put(state, origins, SOURCE_RULES, "constraints", "destination", route[1])
        elif city := rules.find_city(clause):
            _put(state, origins, SOURCE_RULES, "facts", "city", city)

        if money := rules.find_money(clause):
            amount, _is_ceiling = money
            # One budget concept, one path. The old code kept `budget_inr` and
            # `budget_inr_max` apart to preserve "exactly N" vs "at most N" —
            # but a later update only ever patched one of them, leaving the
            # other live and stale. The distinction was not worth a second
            # source of truth for the same number.
            _put(state, origins, SOURCE_RULES, "constraints", "budget.max", amount)

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

        if qty := rules.find_order_quantity(clause):
            _put(state, origins, SOURCE_RULES, "constraints", "quantity", qty)

        if employer := rules.find_employer(clause):
            _put(state, origins, SOURCE_RULES, "facts", "organization", employer)

        if payment := rules.find_payment(clause):
            _put(state, origins, SOURCE_RULES, "preferences", "payment_method", payment)

        if m := rules._REQUIREMENT.search(clause):
            # the trigger word is not enough — "need it before 15 August"
            # matches `need` but names nothing
            if requirement := rules.valid_capture(m.group(1)):
                existing = state.constraints.get("requirements")
                if existing is None:
                    _put(state, origins, SOURCE_RULES, "constraints",
                         "requirements", [requirement])
                elif isinstance(existing, list) and requirement not in existing:
                    state.constraints["requirements"] = rules.prune_subsumed(
                        [*existing, requirement]
                    )

        if m := rules._GOAL.search(clause):
            if goal := rules.valid_capture(m.group(1)):
                _put(state, origins, SOURCE_RULES, "goals", "primary", goal)

        # Generic assignments last: every rule above is higher precision, and
        # `_put` is first-writer-wins, so this only ever fills gaps. It is what
        # lets a message about a flight, a flat or a prescription extract
        # anything at all — the specific rules above only know one domain.
        for path, raw_value in rules.find_alias_assignments(clause, _ALIAS_MATCHER):
            section, key = path.split(".", 1)
            _put(state, origins, SOURCE_RULES, section, key, raw_value)

        for raw_key, raw_value in rules.find_assignments(clause):
            if raw_key:
                _put(state, origins, SOURCE_RULES, _section_for(raw_key), raw_key,
                     raw_value)
            else:
                _put_enum_guess(state, origins, raw_value)

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

# label -> canonical path, generated from the registry rather than written out
# here. A hardcoded list drifts: a field added to the registry would never be
# asked for, and a label kept here after its field was removed would be asked
# for forever. Deriving one from the other makes both true by construction.
GLINER_SCHEMA: dict[str, str] = {
    spec.entity_label: spec.path for spec in canon.REGISTRY
}
GLINER_SCHEMA["unresolved item"] = "unresolved.item"
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

        path = GLINER_SCHEMA[label]
        section, key = path.split(".", 1)

        if section == "unresolved":
            slug = rules.slugify(value)
            if slug and not any(u.field == slug for u in state.unresolved):
                state.unresolved.append(UnresolvedField(field=slug, reason="not provided"))
                origins[f"unresolved.{slug}"] = SOURCE_GLINER
            continue

        if path in ("facts.name", "facts.city"):
            # the same blocklist the rules use — a neural span is no more
            # entitled to name someone "via" than a regex was
            if value.lower() in rules.NAME_STOPWORDS:
                continue
        elif path == "constraints.requirements":
            if not (value := rules.valid_capture(value) or ""):
                continue
            existing = state.constraints.get("requirements")
            if isinstance(existing, list):
                if value not in existing:
                    state.constraints["requirements"] = rules.prune_subsumed(
                        [*existing, value]
                    )
                continue
            value = [value]

        # the model's own score reaches the field's confidence floor, so a
        # hesitant span cannot fill a field that demands certainty
        try:
            confidence = float(score)
        except (TypeError, ValueError):
            confidence = canon.CONFIDENCE[SOURCE_GLINER]
        _put(state, origins, SOURCE_GLINER, section, key, value, confidence=confidence)

    return True


# --- tier 3: LLM structured extraction ----------------------------------------

def _llm_field_menu() -> str:
    """The schema, rendered from the registry rather than written out here.

    A hand-maintained prompt is a second source of truth that silently drifts:
    the previous one still asked for `budget_inr` and `budget_inr_max` long
    after those paths stopped existing, so anything tier 3 returned for a
    budget was rejected on arrival. Generating it means the model is asked for
    exactly what the registry can store, always.
    """
    lines = []
    for spec in canon.REGISTRY:
        if spec.enum_values:
            shape = " | ".join(spec.enum_values)
        elif spec.type == "money":
            shape = 'amount as written, e.g. "75000" or "75k"'
        elif spec.type == "date":
            shape = 'date as written, e.g. "15 Aug" or "next Friday"'
        elif spec.type == "list":
            shape = "array of strings"
        elif spec.type == "int":
            shape = "integer"
        else:
            shape = "string"
        hint = f"   # {spec.description}" if spec.description else ""
        lines.append(f'  "{spec.path}": {shape}{hint}')
    return "\n".join(lines)


def _llm_prompt() -> str:
    return (
        "You extract structured facts from a user message. Reply with STRICT "
        "JSON only - no prose, no markdown fence.\n\n"
        "Return a FLAT object whose keys are chosen from exactly this list. "
        "Omit every key the message does not state:\n\n"
        "{\n" + _llm_field_menu() + "\n}\n\n"
        "Rules:\n"
        "- Never invent a value that is not in the message.\n"
        "- Copy values as the user wrote them; do not reformat dates or money.\n"
        "- Omit a key rather than guess.\n"
        '- Use {"unresolved":[{"field":"...","reason":"..."}]} for something '
        "the user asked about but did not supply."
    )


def _llm_should_run(text: str, state: StructuredState) -> bool:
    """Tier 3 fires when the cheap tiers plainly did not cover the message.

    These are OR-ed, not AND-ed. The previous conjunction meant a long message
    that happened to yield two fields never reached tier 3, so the one tier
    that generalises past the rule vocabulary almost never ran - which is a
    large part of why arbitrary prompts extracted so little.
    """
    if not get_settings().extractor_llm_fallback:
        return False
    words = len(text.split())
    found = field_count(state)
    return (
        # substantive input the tiers below barely touched
        (words >= LLM_MIN_WORDS and found < LLM_MAX_FIELDS)
        or words > LLM_LONG_MESSAGE   # long enough to be carrying more
        or found < words // 12        # dense text, sparse extraction
    )


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
            system_context=_llm_prompt(),
            user_message=text,
        )
        payload = _parse_json(result.get("text") or result.get("content") or "")
    except Exception as exc:  # noqa: BLE001 — no key, no credit, bad JSON: all fine
        logger.info("LLM extraction tier skipped (%s)", exc.__class__.__name__)
        return False
    if not payload:
        return False

    landed = False
    # The prompt asks for a flat, path-keyed object, but a model will
    # sometimes nest it anyway. Both shapes are accepted and flattened to the
    # same pairs — no key reaches state without `_put` resolving it against
    # the registry first, so a hallucinated field name cannot become a fact.
    for raw_key, value in _flatten_llm(payload).items():
        if value in (None, "", [], {}):
            continue
        spec = canon.resolve(raw_key)
        if spec is None:
            _quarantine(state, raw_key, value, SOURCE_LLM)
            continue
        if spec.path in ("facts.name", "facts.city") and \
                str(value).strip().lower() in rules.NAME_STOPWORDS:
            continue
        landed |= _put(state, origins, SOURCE_LLM, spec.section,
                       spec.path.split(".", 1)[1], value)

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


def _flatten_llm(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten a tier-3 reply to `path -> value`, whether flat or nested."""
    out: dict[str, Any] = {}

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{prefix}.{key}" if prefix else str(key))
        elif prefix:
            out[prefix] = node

    for key, value in payload.items():
        if key == "unresolved":
            continue
        # a money/date object is a value, not a container to descend into
        if isinstance(value, dict) and {"value", "iso"} & set(value):
            out[key] = value
        else:
            walk(value, str(key))
    return out


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
