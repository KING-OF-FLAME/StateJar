"""Append-only state evolution for StateJar.

New extracted information is merged into the previous state to produce
a NEW record whose parent_handle points at the old one. The old record
is never modified or deleted — history is immutable by construction.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.conflict import _TRACKED_SECTIONS, detect_conflicts
from app.memory.handle import generate_handle


def _merge(old_state: dict[str, Any], new_extracted: dict[str, Any]) -> dict[str, Any]:
    """Merge new info over the old state (new values win); pure function."""
    merged = copy.deepcopy(old_state)

    for section in _TRACKED_SECTIONS:
        new_section = new_extracted.get(section) or {}
        if new_section:
            merged.setdefault(section, {}).update(copy.deepcopy(new_section))

    # unresolved: union by field name; drop entries now answered by a value
    resolved_fields = set()
    for section in _TRACKED_SECTIONS:
        resolved_fields.update((merged.get(section) or {}).keys())
    unresolved = {
        e["field"]: e
        for e in (old_state.get("unresolved") or []) + (new_extracted.get("unresolved") or [])
        if isinstance(e, dict) and e.get("field") not in resolved_fields
    }
    merged["unresolved"] = list(unresolved.values())

    # carry over prior conflicts; new ones are appended by evolve_state
    merged["conflicts"] = copy.deepcopy(old_state.get("conflicts") or []) + [
        c for c in (new_extracted.get("conflicts") or [])
    ]
    return merged


def evolve_state(
    old_state: dict[str, Any], new_extracted: dict[str, Any], old_handle: str
) -> tuple[dict[str, Any], str]:
    """Merge new info into old state; return (new_state, new_handle).

    The returned state carries parent_handle = old_handle. The caller
    persists it as a new row; the old record is never touched.
    """
    conflicts = detect_conflicts(old_state, new_extracted)

    new_state = _merge(old_state, new_extracted)
    new_state["conflicts"].extend(conflicts)

    canonical = canonicalize(
        {k: v for k, v in new_state.items() if k != "parent_handle"}
    )
    new_handle = generate_handle(canonical, SCHEMA_VERSION, NORM_VERSION)

    # canonical form is the authoritative state content
    new_state = json.loads(canonical)
    new_state["parent_handle"] = old_handle
    return new_state, new_handle
