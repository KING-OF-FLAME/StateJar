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

logger = logging.getLogger(__name__)

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
            "conflicts.constraints*",
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
MODE_BROAD = "broad_fallback"     # no intent and nothing semantic to add

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
        (f"{section}.{key}", f"{section}.{key}: {_render(field_value)}")
        for section, value in full_state.items()
        if isinstance(value, dict)
        for key, field_value in value.items()
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


def retrieve_minimum(query: str, full_state: dict[str, Any]) -> dict[str, Any]:
    """Return the minimal state subset needed to answer `query`, with metadata."""
    intents = classify_intents(query)
    patterns: list[str] = []
    for intent in intents:
        patterns.extend(INTENT_FIELD_MAP[intent]["fields"])

    # The semantic layer is a fallback, never an override: it is consulted
    # only when the intent map found nothing, so an enabled model can never
    # change the subset for a query that already matched.
    mode = MODE_INTENT if intents else MODE_BROAD
    semantic_hits: set[str] = set()
    if not intents and _semantic_enabled():
        matched = _semantic_fields(query, full_state)
        if matched:
            semantic_hits = set(matched)
            mode = MODE_SEMANTIC

    subset: dict[str, Any] = {}
    subset_keys: list[str] = []

    # dict sections (facts/preferences/decisions/constraints/goals)
    for section, value in full_state.items():
        if not isinstance(value, dict):
            continue
        for key, field_value in value.items():
            dotted = f"{section}.{key}"
            if any(fnmatch(dotted, pat) for pat in patterns) or dotted in semantic_hits:
                subset.setdefault(section, {})[key] = field_value
                subset_keys.append(dotted)

    # unresolved / conflicts: keep entries whose `field` relates to the subset
    selected_leaves = {k.split(".", 1)[1] for k in subset_keys}
    for section in ("unresolved", "conflicts"):
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

    full_leaves = _leaf_paths(
        {k: v for k, v in full_state.items() if k not in ("unresolved", "conflicts")}
    )
    n_full = len(full_leaves) + sum(
        len(full_state.get(s) or []) for s in ("unresolved", "conflicts")
    )
    fields_dropped = n_full - len(subset_keys)

    full_json = json.dumps(full_state, ensure_ascii=False)
    subset_json = json.dumps(subset, ensure_ascii=False)
    saved_pct = round(100 * (1 - len(subset_json) / len(full_json)), 1) if full_json else 0.0

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
