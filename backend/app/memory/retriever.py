"""Minimal-subset state retrieval for StateJar.

Given a user query and a full structured state, return only the fields
the query actually needs (patent: minimal disclosure / token-efficient
context injection), plus unresolved/conflict entries related to those
fields.

This is a READ path only. It never writes, never mutates the state it is
given, and nothing it computes reaches canonicalization — so no option
here can change a handle. That is what makes the optional semantic layer
below safe to enable: identity is decided entirely on the write path.

An optional sentence-transformers fallback can be switched on with
RETRIEVER_SEMANTIC=true. It runs only when the keyword intent map matched
nothing, so with it off (the default) behaviour is bit-for-bit today's.
"""

from __future__ import annotations

import json
import logging
import math
import re
from fnmatch import fnmatch
from typing import Any

from app.config import get_settings
from app.schema import canonical as canon
from app.schema import dynamic as dyn

logger = logging.getLogger(__name__)

# Never disclosed to a model, whatever the query asks for.
#
# `conflicts` is the important one. A conflict record carries the value that
# was *superseded* — so disclosing it handed the model the stale figure the
# canonical layer had just finished removing from active state, by a second
# route. It is a record of how state changed, not a thing the user told us.
# Quarantine is not fact, and history is by definition not current.
_NEVER_DISCLOSED = ("_unmapped", "history", "reinforced", "conflicts")

# Intent → keywords that trigger it and the dotted field patterns it needs.
# Patterns support fnmatch wildcards on the leaf (e.g. "constraints.budget*").
# "unresolved.X*" / "conflicts.X*" select list entries whose `field` matches.
INTENT_FIELD_MAP: dict[str, dict[str, list[str]]] = {
    "booking": {
        "keywords": ["book", "order", "delivery", "purchase", "buy", "reserve"],
        "fields": [
            "preferences.contact_mode",
            "constraints.budget*",
            "unresolved.delivery*",
        ],
    },
    "contact": {
        "keywords": ["contact", "call", "email", "reach", "whatsapp", "message"],
        "fields": ["preferences.contact_mode", "unresolved.contact*"],
    },
    "budget": {
        "keywords": ["budget", "price", "cost", "afford", "expensive", "cheap"],
        "fields": ["constraints.*", "unresolved.budget*"],
    },
    "identity": {
        "keywords": ["name", "who am i", "profile"],
        "fields": ["facts.*"],
    },
    "goals": {
        "keywords": ["goal", "plan", "objective", "want"],
        "fields": ["goals.*"],
    },
    # Briefing a coding assistant: a follow-up like "now add a pricing
    # section" needs the build spec and nothing else — not the audience, and
    # certainly not the earlier transcript.
    "build": {
        "keywords": [
            "add", "build", "create", "implement", "page", "section",
            "component", "layout", "style", "design", "screen", "form",
        ],
        "fields": [
            "decisions.stack",
            "preferences.theme",
            "preferences.brand_color",
            "constraints.no_ui_libs",
            "unresolved.stack*",
        ],
    },
}


def classify_intents(query: str) -> list[str]:
    """Return all intents whose keywords appear in the query."""
    words = re.findall(r"[a-z]+", query.lower())
    text = " ".join(words)
    intents = []
    for intent, spec in INTENT_FIELD_MAP.items():
        for kw in spec["keywords"]:
            if (kw in words) if " " not in kw else (kw in text):
                intents.append(intent)
                break
    return intents


# --- optional semantic fallback -----------------------------------------------

# How the subset was chosen, reported as `metadata.retrieval_mode`.
MODE_INTENT = "intent_map"        # the keyword map matched — the normal path
MODE_SEMANTIC = "semantic_fallback"  # no intent, embeddings picked the fields
MODE_FIELDS = "field_match"       # the query named a field the state holds
MODE_BROAD = "broad_fallback"     # no intent and nothing semantic to add
MODE_FULL = "full_state"          # small enough that selecting saves nothing

# Phrases that ask for what StateJar already knows, rather than naming a
# field. These are the whole point of the product, and the keyword map scored
# them at zero.
_RECALL_PHRASES = (
    "saved preferences", "my preferences", "my usual", "as usual",
    "like last time", "same as last time", "my details", "my usual details",
    "on file", "you already know", "what you know about me", "my profile",
    "my saved", "remember", "previous", "last time",
)

# What "my preferences" resolves to: the whole preference and constraint
# namespaces, plus identity. Small, and cheap relative to being wrong.
RECALL_FIELDS = ["preferences.*", "constraints.*", "facts.*",
                 "unresolved.*", "goals.*", "decisions.*"]

# Rough chars-per-token. The threshold itself is configurable — see
# Settings.retriever_full_state_tokens for why it exists and what 0 means.
_CHARS_PER_TOKEN = 4


def _wants_everything_known(query: str) -> bool:
    lowered = " ".join(query.lower().split())
    return any(phrase in lowered for phrase in _RECALL_PHRASES)


def _disclosable(full_state: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in full_state.items() if k not in _NEVER_DISCLOSED}


def _is_small(full_state: dict[str, Any]) -> bool:
    budget = get_settings().retriever_full_state_tokens * _CHARS_PER_TOKEN
    if budget <= 0:
        return False
    return len(json.dumps(_disclosable(full_state), ensure_ascii=False)) <= budget

SEMANTIC_MODEL_NAME = "all-MiniLM-L6-v2"
SEMANTIC_THRESHOLD = 0.45
SEMANTIC_TOP_K = 5

# Loaded at most once per process; a failed attempt is never retried, so a
# deployment without the ML extras costs one log line rather than a stall
# on every query.
_semantic_state: dict[str, Any] = {"attempted": False, "model": None}


def _semantic_enabled() -> bool:
    return get_settings().retriever_semantic


def _load_semantic_model() -> Any | None:
    """Import and load the embedding model once. Returns None on any failure."""
    if _semantic_state["attempted"]:
        return _semantic_state["model"]
    _semantic_state["attempted"] = True
    try:  # pragma: no cover - requires the optional ML extras
        # imported here, not at module scope: torch is slow to import and is
        # absent in production
        from sentence_transformers import SentenceTransformer

        _semantic_state["model"] = SentenceTransformer(SEMANTIC_MODEL_NAME)
        logger.info("Semantic retrieval fallback loaded (%s)", SEMANTIC_MODEL_NAME)
    except Exception as exc:  # noqa: BLE001 — missing extras must never crash
        logger.warning(
            "sentence-transformers unavailable (%s: %s) — retrieval stays on the "
            "intent map. Install backend/requirements-ml.txt to enable it.",
            exc.__class__.__name__,
            exc,
        )
        _semantic_state["model"] = None
    return _semantic_state["model"]


def _render(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity, in plain Python so mocked vectors work without numpy."""
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _semantic_fields(query: str, full_state: dict[str, Any]) -> list[str] | None:
    """Dotted paths whose `path: value` text is semantically close to `query`.

    Returns the top `SEMANTIC_TOP_K` above `SEMANTIC_THRESHOLD`, or None when
    the model could not run at all (so the caller can tell "nothing matched"
    apart from "the layer is unavailable").

    Only the dict sections are embedded; unresolved/conflict entries are then
    pulled in by the existing relatedness rule, exactly as in intent mode.
    """
    model = _load_semantic_model()
    if model is None:
        return None

    candidates = [
        (path, f"{path}: {_render(canon.read_path(full_state, path))}")
        for section, value in full_state.items()
        if isinstance(value, dict) and section not in _NEVER_DISCLOSED
        for path in canon.leaf_paths_in(value, section)
    ]
    if not candidates:
        return []

    try:
        vectors = model.encode([query] + [text for _, text in candidates])
        query_vec = [float(x) for x in vectors[0]]
        scored = [
            (dotted, _cosine(query_vec, [float(x) for x in vectors[i + 1]]))
            for i, (dotted, _) in enumerate(candidates)
        ]
    except Exception as exc:  # noqa: BLE001 — a bad embedding must not 500
        logger.warning("Semantic retrieval failed (%s) — using the intent map", exc)
        return None

    hits = [(d, s) for d, s in scored if s > SEMANTIC_THRESHOLD]
    # score first, then path, so equal scores resolve deterministically
    hits.sort(key=lambda item: (-item[1], item[0]))
    return [dotted for dotted, _ in hits[:SEMANTIC_TOP_K]]


def _all_field_paths(full_state: dict[str, Any]) -> list[str]:
    """Every canonical field in the state — the baseline the saving is against.

    Stops at canonical leaves. Counting into a normalized value would score
    `constraints.budget.max` as two fields (its amount and its currency) and
    quietly inflate the token-saving figure.
    """
    return [
        path
        for section, value in full_state.items()
        if isinstance(value, dict) and section not in _NEVER_DISCLOSED
        for path in canon.leaf_paths_in(value, section)
    ]


def _leaf_paths(value: Any, prefix: str = "") -> list[str]:
    """All dotted leaf paths in a nested dict (lists count as single leaves)."""
    if isinstance(value, dict) and value:
        paths: list[str] = []
        for key, sub in value.items():
            dotted = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_leaf_paths(sub, dotted))
        return paths
    return [prefix] if prefix else []


def _entry_field(entry: Any) -> str:
    return str(entry.get("field", "")) if isinstance(entry, dict) else str(entry)


def _forms(word: str) -> set[str]:
    """A word and its singular, for matching only.

    `dyn._same_word` needs a four-character shared stem, so "kits" and "kit"
    do not match — and "how many kits can the budget cover" then misses
    `dynamic.kit_invoice`, which is exactly the field the answer needs. Handled
    here rather than by loosening the shared stemmer: that one also decides
    which concept a retraction removes, and it reaches the stored state.
    """
    forms = {word}
    for suffix in ("es", "s"):
        if len(word) > len(suffix) + 1 and word.endswith(suffix):
            forms.add(word[: -len(suffix)])
    return forms


def _fields_named_in(query: str, full_state: dict[str, Any]) -> set[str]:
    """Fields the query names outright, matched against the state's own paths.

    `INTENT_FIELD_MAP` is a fixed keyword list built around shopping and code
    briefs. Nothing in it can classify "how many trucks do we have" — so on
    every domain it was not written for, the map scores zero and selection
    falls through to disclosing everything.

    This asks a different question: does the query mention a field this state
    actually has? "trucks" and `dynamic.truck_count` share a word once both are
    stemmed, so the field is selected. "Tell me a joke" shares a word with
    nothing, so nothing is selected and minimal disclosure is preserved — which
    is the property that makes this safe to run before the size fallback.

    Domain-agnostic by construction: it reads the field names in front of it
    rather than a vocabulary someone has to remember to extend.
    """
    wanted = {v for w in dyn.content_words(query) for v in _forms(w)}
    if not wanted:
        return set()

    hits: set[str] = set()
    for section, block in full_state.items():
        if not isinstance(block, dict) or section in _NEVER_DISCLOSED:
            continue
        for dotted in canon.leaf_paths_in(block, section):
            # the leaf, not the section: "constraints.budget.max" is named by
            # "budget", and nobody asks about "constraints"
            leaf = dotted.split(".", 1)[1].replace("_", " ").replace(".", " ")
            leaf_words = {v for w in dyn.content_words(leaf) for v in _forms(w)}
            if wanted & leaf_words or any(
                dyn._same_word(w, l) for w in wanted for l in leaf_words
            ):
                hits.add(dotted)
    return hits


def retrieve_minimum(query: str, full_state: dict[str, Any]) -> dict[str, Any]:
    """Return the minimal state subset needed to answer `query`, with metadata."""
    intents = classify_intents(query)
    patterns: list[str] = []
    for intent in intents:
        patterns.extend(INTENT_FIELD_MAP[intent]["fields"])

    # "use my saved preferences" is a request for a whole namespace, not a
    # keyword to score. It used to match nothing and return 3 of 12 fields.
    if _wants_everything_known(query):
        patterns.extend(RECALL_FIELDS)

    # The semantic layer is a fallback, never an override: it is consulted
    # only when the intent map found nothing, so an enabled model can never
    # change the subset for a query that already matched.
    # Fields the query names outright. Added to whatever the keyword map found
    # rather than used only when it found nothing: the map's patterns are
    # coarse, and "how many kits can the budget cover" matches the budget
    # intent, which returns `constraints.*` and leaves `dynamic.kit_invoice`
    # behind — the query names both, and the answer needs both. Union only, so
    # this can widen a subset and never narrow one.
    named = _fields_named_in(query, full_state)
    mode = MODE_INTENT if patterns else (MODE_FIELDS if named else MODE_BROAD)
    semantic_hits: set[str] = set(named)

    # The semantic layer is a fallback, never an override: it is consulted
    # only when nothing cheaper matched, so an enabled model can never change
    # the subset for a query that already matched.
    if not patterns and not semantic_hits and _semantic_enabled():
        matched = _semantic_fields(query, full_state)
        if matched:
            semantic_hits = set(matched)
            mode = MODE_SEMANTIC

    # Below this size there is nothing worth saving, and a wrong answer costs
    # far more than the handful of tokens a narrower subset would have saved.
    # Selective retrieval is an optimisation; it must never be the reason an
    # answer is wrong. Above the threshold, selection engages as before.
    if _is_small(full_state):
        patterns = ["*"]
        mode = MODE_FULL

    subset: dict[str, Any] = {}
    subset_keys: list[str] = []

    # dict sections (facts/preferences/decisions/constraints/goals). Selection
    # is per canonical *path*: a money or date value is one field, not a
    # sub-object to be disclosed a piece at a time.
    for section, value in full_state.items():
        if not isinstance(value, dict) or section in _NEVER_DISCLOSED:
            continue
        for dotted in canon.leaf_paths_in(value, section):
            if any(fnmatch(dotted, pat) for pat in patterns) or dotted in semantic_hits:
                canon.write_path(subset, dotted, canon.read_path(full_state, dotted))
                subset_keys.append(dotted)

    # unresolved: keep entries whose `field` relates to the subset. Conflicts
    # are deliberately absent — see _NEVER_DISCLOSED.
    selected_leaves = {k.split(".", 1)[1] for k in subset_keys}
    for section in ("unresolved",):
        entries = full_state.get(section) or []
        kept = []
        for entry in entries:
            field = _entry_field(entry)
            dotted = f"{section}.{field}"
            if any(fnmatch(dotted, pat) for pat in patterns) or field in selected_leaves:
                kept.append(entry)
                subset_keys.append(dotted)
        if kept:
            subset[section] = kept

    full_leaves = _all_field_paths(full_state)
    n_full = len(full_leaves) + len(full_state.get("unresolved") or [])
    fields_dropped = n_full - len(subset_keys)

    # Measured against what a naive client would have sent — the disclosable
    # state — rather than the whole record. Reporting a saving against bytes
    # that were never eligible for disclosure would flatter the number.
    # This is computed after selection and never feeds back into it.
    full_json = json.dumps(_disclosable(full_state), ensure_ascii=False)
    subset_json = json.dumps(subset, ensure_ascii=False)
    saved_pct = round(100 * (1 - len(subset_json) / len(full_json)), 1) if full_json else 0.0
    saved_pct = max(saved_pct, 0.0)

    return {
        "subset": subset,
        "metadata": {
            "intents": intents,
            "retrieval_mode": mode,
            "subset_keys": subset_keys,
            "fields_dropped": fields_dropped,
            "token_estimate_saved_pct": saved_pct,
        },
    }
