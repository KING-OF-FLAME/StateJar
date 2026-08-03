"""Dynamic fields — concepts StateJar was never told about in advance.

The registry can only hold what someone thought to declare. Everything else
went to `_unmapped` and was therefore invisible: a kiln schedule, a feed
conversion ratio, a GSTIN and a container load limit were all present in the
message, seen by the extractor, and stored nowhere.

Adding `max_load`, `insured_value` and `turnover` to the alias table is the
word-by-word approach and it has no end. Instead a fact that does not map to a
registry path becomes a **dynamic field**: same normalizers, same lifecycle,
same duplicate-path invariant, part of the handle, retrievable and versionable.
Dynamic fields are state. They are not `unresolved` and they are not
`_unmapped` — `_unmapped` now means "failed a guard", never "unfamiliar".

Concept reuse happens here too, and without embeddings. Two names for one
thing ("max load per container", "container load limit") are reconciled by
content-word containment, and an update that names a qualifier can find its
target by that qualifier alone. Both rules are deterministic, which is what
lets a dynamic field be part of a content-addressed handle at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any

from app.schema import normalizers as norm
from app.schema import valuetype as vt

SECTION = "dynamic"

# The qualifiers an extractor may attach to a concept. A closed set, because
# these become path segments and an open one would fragment a concept across
# a dozen spellings of "maximum".
QUALIFIERS = (
    "min", "max", "start", "end", "from", "to", "before", "after",
    "current", "previous", "target", "actual",
)
QUALIFIER_SYNONYMS = {
    "minimum": "min", "lowest": "min", "least": "min", "floor": "min",
    "maximum": "max", "highest": "max", "most": "max", "cap": "max",
    "ceiling": "max", "limit": "max", "upper": "max",
    "starting": "start", "begin": "start", "beginning": "start",
    "commence": "start", "opens": "start", "departure": "start",
    "ending": "end", "finish": "end", "close": "end", "closes": "end",
    "arrival": "end",
    # "deadline" is deliberately absent: it is a registry field in its own
    # right, and treating it as a synonym for "end" sent every deadline to
    # a dynamic field instead.
    "now": "current", "today": "current", "present": "current",
    "prior": "previous", "last": "previous", "old": "previous",
    "goal": "target", "planned": "target", "expected": "target",
    "real": "actual", "measured": "actual",
}

POLARITY_ASSERT = "assert"
POLARITY_NEGATE = "negate"
POLARITY_RETRACT = "retract"
POLARITIES = (POLARITY_ASSERT, POLARITY_NEGATE, POLARITY_RETRACT)

# Words carried along by a concept phrase that say nothing about which concept
# it is. Dropped before two concept names are compared.
_CONCEPT_STOPWORDS = frozenset({
    "the", "a", "an", "my", "our", "your", "its", "their", "this", "that",
    "of", "for", "per", "in", "on", "at", "to", "by", "with", "and", "or",
    "is", "are", "was", "were", "be", "value", "amount", "number", "level",
    *QUALIFIERS, *QUALIFIER_SYNONYMS,
})


@dataclass(frozen=True)
class Fact:
    """One thing a message asserted, before it is routed anywhere.

    This is the extractor's whole output vocabulary. `concept` is free text —
    there is no allowed set — which is the point: an extractor handed a fixed
    field list can only ever return that list, and returning "Not provided"
    for 35 registry fields is not extraction.
    """

    concept: str
    value: Any
    value_type: str = vt.TEXT
    qualifier: str | None = None
    polarity: str = POLARITY_ASSERT
    confidence: float = 1.0
    span: tuple[int, int] | None = None
    unit: str | None = None
    source: str = "rules"

    def with_concept(self, concept: str) -> "Fact":
        return Fact(concept, self.value, self.value_type, self.qualifier,
                    self.polarity, self.confidence, self.span, self.unit,
                    self.source)


# --- naming -------------------------------------------------------------------

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify_concept(concept: str) -> str:
    """A concept name to a stable path segment."""
    slug = _SLUG_STRIP.sub("_", str(concept or "").strip().lower()).strip("_")
    return slug[:60]


def normalize_qualifier(qualifier: str | None) -> str | None:
    """Fold a qualifier to the closed set, or None."""
    if not qualifier:
        return None
    text = str(qualifier).strip().lower()
    if text in QUALIFIERS:
        return text
    return QUALIFIER_SYNONYMS.get(text)


def content_words(concept: str) -> frozenset[str]:
    """The words that identify a concept, with qualifiers and filler removed."""
    words = _SLUG_STRIP.sub(" ", str(concept or "").lower()).split()
    return frozenset(w for w in words if w and w not in _CONCEPT_STOPWORDS)


_STEM_MIN = 4


def _same_word(a: str, b: str) -> bool:
    """Two surface forms of one word, by shared prefix.

    "insurance" and "insured" are the same concept said twice; requiring exact
    equality means a retraction phrased differently from the assertion silently
    does nothing. A shared four-character prefix is crude, but it is
    deterministic and needs no stemmer — which matters, because this decides
    what stays in a hashed state.
    """
    if a == b:
        return True
    shortest = min(len(a), len(b))
    if shortest < _STEM_MIN:
        return False
    shared = 0
    for x, y in zip(a, b):
        if x != y:
            break
        shared += 1
    # enough shared prefix in absolute terms *and* relative to the shorter
    # word, so "insurance"/"insured" match while "container"/"contact" do not
    return shared >= _STEM_MIN and shared >= shortest * 0.6


def words_cover(wanted: frozenset[str], have: frozenset[str]) -> bool:
    """Whether every word in `wanted` has a match in `have`."""
    if not wanted:
        return False
    return all(any(_same_word(w, h) for h in have) for w in wanted)


def split_qualifier(concept: str) -> tuple[str, str | None]:
    """Pull a leading or trailing qualifier out of a concept phrase.

    "max load per container" is the concept "load per container" with the
    qualifier "max" — keeping them fused would make the same limit a different
    field every time someone phrased it differently.
    """
    words = _SLUG_STRIP.sub(" ", str(concept or "").lower()).split()
    qualifier = None
    while words:
        candidate = normalize_qualifier(words[0])
        if candidate is None:
            break
        qualifier, words = candidate, words[1:]
    while words:
        candidate = normalize_qualifier(words[-1])
        if candidate is None:
            break
        qualifier, words = qualifier or candidate, words[:-1]
    return " ".join(words), qualifier


def path_for(concept: str, qualifier: str | None) -> str:
    slug = slugify_concept(concept)
    return f"{SECTION}.{slug}.{qualifier}" if qualifier else f"{SECTION}.{slug}"


# --- concept reuse (no embeddings) --------------------------------------------

MIN_SHARED_WORDS = 2


def reconcile_concept(
    concept: str, known: list[str], qualifier: str | None = None,
    qualifier_index: dict[str, list[str]] | None = None,
) -> str:
    """Map a concept onto one already in this session, or keep it as it is.

    Two deterministic rules, in order:

      1. Content-word containment. "container load" is a subset of
         "container load limit" and shares two identifying words, so they are
         the same slot. One shared word is not enough — "booking date" and
         "delivery date" would collapse.
      2. Qualifier uniqueness. An update that names a qualifier and nothing
         else ("push the **end** date") belongs to whichever concept already
         carries that qualifier, when exactly one does.

    No vector store and no threshold, so the same message always lands on the
    same slot — which is what allows a dynamic field to be part of a handle.
    """
    if not known:
        return concept
    if concept in known:
        return concept

    mine = content_words(concept)
    if mine:
        best: tuple[int, str] | None = None
        for candidate in known:
            theirs = content_words(candidate)
            if not theirs:
                continue
            shared = mine & theirs
            if not (mine <= theirs or theirs <= mine):
                continue
            if len(shared) < MIN_SHARED_WORDS and mine != theirs:
                continue
            # most shared words wins; the name itself breaks a tie so the
            # result cannot depend on dict ordering
            key = (len(shared), candidate)
            if best is None or key > (best[0], best[1]):
                best = key
        if best is not None:
            return best[1]

    if qualifier and qualifier_index:
        owners = qualifier_index.get(qualifier) or []
        if len(owners) == 1 and not mine:
            return owners[0]
        # a concept whose only content word is generic ("date", "figure")
        # still belongs to the one slot carrying that qualifier
        if len(owners) == 1 and mine <= content_words(owners[0]) | mine and len(mine) <= 1:
            return owners[0]
    return concept


def qualifier_index(state: dict[str, Any]) -> dict[str, list[str]]:
    """qualifier -> the concepts that currently carry it."""
    out: dict[str, list[str]] = {}
    block = state.get(SECTION)
    if not isinstance(block, dict):
        return out
    for slug, entry in block.items():
        if not isinstance(entry, dict):
            continue
        for key, sub in entry.items():
            if key in QUALIFIERS and isinstance(sub, dict):
                out.setdefault(key, []).append(_concept_of(entry, slug))
    return out


def known_concepts(state: dict[str, Any]) -> list[str]:
    """Every concept name already in this session, oldest-stable order."""
    block = state.get(SECTION)
    if not isinstance(block, dict):
        return []
    return sorted(_concept_of(entry, slug) for slug, entry in block.items())


def _concept_of(entry: Any, slug: str) -> str:
    if isinstance(entry, dict):
        for candidate in entry.values():
            if isinstance(candidate, dict) and candidate.get("concept"):
                return str(candidate["concept"])
        if entry.get("concept"):
            return str(entry["concept"])
    return slug.replace("_", " ")


# --- value normalization ------------------------------------------------------

# Physical values are stored in a base unit so that two spellings of the same
# measurement are the same value. "1,240 kg" and "1.24 tonnes" both become
# 1240000 g — without that they would read as a contradiction and the
# correction in the message would be logged as a conflict.
_BASE_UNITS: dict[str, tuple[str, float]] = {
    "g": ("g", 1.0), "kg": ("g", 1_000.0), "tonnes": ("g", 1_000_000.0),
    "quintal": ("g", 100_000.0), "lb": ("g", 453.59237),
    "ml": ("ml", 1.0), "l": ("ml", 1_000.0), "gal": ("ml", 3785.411784),
    "mm": ("mm", 1.0), "cm": ("mm", 10.0), "m": ("mm", 1_000.0),
    "km": ("mm", 1_000_000.0), "ft": ("mm", 304.8), "in": ("mm", 25.4),
    "sqft": ("sqft", 1.0), "sqm": ("sqft", 10.7639104),
    "b": ("b", 1.0), "kb": ("b", 1_000.0), "mb": ("b", 1_000_000.0),
    "gb": ("b", 1_000_000_000.0), "tb": ("b", 1_000_000_000_000.0),
    "seconds": ("seconds", 1.0), "minutes": ("seconds", 60.0),
    "hours": ("seconds", 3_600.0), "days": ("seconds", 86_400.0),
    "weeks": ("seconds", 604_800.0), "months": ("seconds", 2_592_000.0),
    "years": ("seconds", 31_536_000.0),
}

# Float arithmetic makes 1.24 * 1e6 land a hair off 1240000. Rounding to six
# decimals is far below any real measurement precision and makes the two
# spellings compare equal, which is the entire reason for a base unit.
_BASE_PRECISION = 6


def to_base(number: float, unit: str | None) -> tuple[float, str | None]:
    if not unit or unit not in _BASE_UNITS:
        return number, unit
    base, factor = _BASE_UNITS[unit]
    return round(number * factor, _BASE_PRECISION), base


def normalize_value(value: Any, value_type: str, *, context: str = "") -> dict | None:
    """A raw value plus its declared kind to a stored envelope, or None.

    None means the value failed its own type's normalizer — the same
    fail-closed rule the registry fields follow.
    """
    if value is None or value == "":
        return None
    text = str(value).strip()

    if value_type == vt.MONEY:
        money = norm.normalize_money(text)
        return {"type": vt.MONEY, **money} if money else None

    if value_type == vt.DATE:
        parsed = norm.normalize_date(text)
        return {"type": vt.DATE, "iso": parsed["iso"], "raw": parsed["raw"]} if parsed else None

    if value_type in (vt.QUANTITY, vt.DURATION):
        reading = vt.classify(text, context=context)
        number = reading.number if reading.number is not None else vt.parse_number(text)
        if number is None:
            return None
        magnitude, unit = to_base(number, reading.unit)
        envelope = {"type": value_type, "value": magnitude}
        if unit:
            envelope["unit"] = unit
        return envelope

    if value_type in (vt.COUNT, vt.PERCENT, vt.RATIO):
        number = vt.parse_number(re.sub(r"[^\d.,]", "", text) or text)
        if number is None:
            reading = vt.classify(text, context=context)
            number = reading.number
        if number is None:
            return None
        if value_type == vt.COUNT:
            number = int(number)
        return {"type": value_type, "value": number}

    if value_type == vt.IDENTIFIER:
        cleaned = norm.normalize_string(text)
        return {"type": vt.IDENTIFIER, "value": cleaned} if cleaned else None

    cleaned = norm.normalize_string(text)
    return {"type": "categorical", "value": cleaned} if cleaned else None


def envelope(fact: Fact, value: dict) -> dict:
    """The stored form. `concept` rides along so the original phrasing
    survives slugification and can be shown back to the user."""
    return {**value, "concept": fact.concept}


# --- routing ------------------------------------------------------------------

ROUTE_REGISTRY = "registry"
ROUTE_DYNAMIC = "dynamic"
ROUTE_REFUSED = "refused"


@dataclass(frozen=True)
class Routed:
    where: str
    path: str | None = None
    value: Any = None
    reason: str = ""


def _qualifier_of_path(path: str) -> str | None:
    leaf = path.rsplit(".", 1)[-1]
    return leaf if leaf in QUALIFIERS else None


def route(fact: Fact, *, context: str = "") -> Routed:
    """Where a fact belongs: a registry path, a dynamic field, or nowhere.

    Registry first, but only on a *clean* map — the concept has to resolve and
    the qualifier has to agree. A fact qualified "start" does not belong in
    `constraints.deadline`, which has no notion of start or end; putting it
    there is what let "push the end date" overwrite a booking's start date.

    A value the registry refuses on type grounds is not discarded. It keeps
    its own concept and becomes a dynamic field, because the value was real —
    it was only ever the destination that was wrong. Quarantine is for values
    that are not anything: those that fail their own type's normalizer.
    """
    from app.schema import canonical as canon   # local: canonical imports this

    if fact.polarity != POLARITY_ASSERT:
        return Routed(ROUTE_REFUSED, reason="not an assertion")

    concept, embedded = split_qualifier(fact.concept)
    qualifier = normalize_qualifier(fact.qualifier) or embedded
    concept = concept or fact.concept

    spec = canon.resolve(fact.concept) or canon.resolve(concept)
    if spec is not None:
        spec_qualifier = _qualifier_of_path(spec.path)
        if qualifier is None or qualifier == spec_qualifier:
            resolved = canon.canonicalize(spec.path, fact.value, context=context,
                                          confidence=fact.confidence)
            if resolved is not None:
                return Routed(ROUTE_REGISTRY, resolved[0], resolved[1])

    value = normalize_value(fact.value, fact.value_type, context=context)
    if value is None:
        return Routed(ROUTE_REFUSED, reason="rejected_value")
    return Routed(ROUTE_DYNAMIC, path_for(concept, qualifier),
                  envelope(fact.with_concept(concept), value))


__all__ = [
    "SECTION", "QUALIFIERS", "QUALIFIER_SYNONYMS", "POLARITIES",
    "POLARITY_ASSERT", "POLARITY_NEGATE", "POLARITY_RETRACT",
    "Fact", "slugify_concept", "normalize_qualifier", "content_words",
    "split_qualifier", "path_for", "reconcile_concept", "qualifier_index",
    "known_concepts", "normalize_value", "envelope", "to_base",
    "words_cover", "route", "Routed", "ROUTE_REGISTRY", "ROUTE_DYNAMIC",
    "ROUTE_REFUSED",
]
