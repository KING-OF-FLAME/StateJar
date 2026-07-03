"""Minimal-subset state retrieval for StateJar.

Given a user query and a full structured state, return only the fields
the query actually needs (patent: minimal disclosure / token-efficient
context injection), plus unresolved/conflict entries related to those
fields.
"""

from __future__ import annotations

import json
import re
from fnmatch import fnmatch
from typing import Any

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

    subset: dict[str, Any] = {}
    subset_keys: list[str] = []

    # dict sections (facts/preferences/decisions/constraints/goals)
    for section, value in full_state.items():
        if not isinstance(value, dict):
            continue
        for key, field_value in value.items():
            dotted = f"{section}.{key}"
            if any(fnmatch(dotted, pat) for pat in patterns):
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
            "subset_keys": subset_keys,
            "fields_dropped": fields_dropped,
            "token_estimate_saved_pct": saved_pct,
        },
    }
