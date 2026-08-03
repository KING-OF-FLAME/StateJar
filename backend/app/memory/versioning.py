"""Append-only state evolution for StateJar.

New extracted information is merged into the previous state to produce
a NEW record whose parent_handle points at the old one. The old record
is never modified or deleted — history is immutable by construction.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize
from app.memory.conflict import _TRACKED_SECTIONS, compare
from app.memory.handle import generate_handle
from app.schema import canonical as canon
from app.schema import dynamic as dyn

# Audit artifacts: preserved on the record, deliberately excluded from the
# bytes that produce the handle.
#
# A conflict record carries the wall-clock instant it was noticed, so hashing
# it made the handle a function of *when* a state was observed rather than of
# what it says. The same input replayed a second later produced a different
# handle, which is the one property a content-addressed store cannot give up.
# `_unmapped` is excluded for the plainer reason that quarantine is not state.
UNHASHED_KEYS = ("conflicts", "history", "_unmapped", "reinforced",
                 "retractions", "parent_handle", "state_version")

STATE_VERSION = 2  # 1 = pre-registry raw keys; 2 = canonical paths


def _item_key(value: Any) -> str:
    """Total order over arbitrary JSON values, for deterministic list unions."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _merge_field(old_value: Any, new_value: Any) -> Any:
    """New value wins, except list-valued fields, which accumulate.

    A list means the field collects rather than replaces (e.g. the
    requirements the extractor gathers): a later message mentioning one more
    requirement must not drop the ones already known. The union is sorted so
    the canonical bytes never depend on the order messages arrived in.
    """
    if isinstance(old_value, list) and isinstance(new_value, list):
        union = list(old_value) + [v for v in new_value if v not in old_value]
        return sorted(union, key=_item_key)
    return copy.deepcopy(new_value)


def _merge(old_state: dict[str, Any], new_extracted: dict[str, Any]) -> dict[str, Any]:
    """Merge new info over the old state (new values win); pure function.

    Merging walks canonical *paths* rather than a section's top-level keys, so
    a nested field like `constraints.budget.max` replaces only itself and
    leaves any sibling under `budget` intact.
    """
    merged = copy.deepcopy(old_state)

    for section in _TRACKED_SECTIONS:
        new_section = new_extracted.get(section) or {}
        if not new_section:
            continue
        merged.setdefault(section, {})
        for path in canon.leaf_paths_in(new_section, section):
            new_value = canon.read_path(new_extracted, path)
            canon.write_path(
                merged, path, _merge_field(canon.read_path(merged, path), new_value)
            )

    # unresolved: union by field name; drop entries now answered by a value
    resolved_fields = set()
    for section in _TRACKED_SECTIONS:
        resolved_fields.update(canon.leaf_paths_in(merged.get(section), section))
        resolved_fields.update((merged.get(section) or {}).keys())
    unresolved = {
        e["field"]: e
        for e in (old_state.get("unresolved") or []) + (new_extracted.get("unresolved") or [])
        if isinstance(e, dict)
        and e.get("field") not in resolved_fields
        and f"{e.get('section', '')}.{e.get('field')}" not in resolved_fields
    }
    merged["unresolved"] = list(unresolved.values())

    # quarantine accumulates so the registry can be grown from real misses
    unmapped = {**(old_state.get("_unmapped") or {}), **(new_extracted.get("_unmapped") or {})}
    unmapped.update(new_extracted.get("unmapped") or {})
    if unmapped:
        merged["_unmapped"] = unmapped
    merged.pop("unmapped", None)

    # carry over prior conflicts; new ones are appended by evolve_state
    merged["conflicts"] = copy.deepcopy(old_state.get("conflicts") or []) + [
        c for c in (new_extracted.get("conflicts") or [])
    ]
    merged["history"] = copy.deepcopy(old_state.get("history") or [])
    merged["reinforced"] = dict(old_state.get("reinforced") or {})
    return merged


def _seal(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Canonicalize, hash, then re-attach the audit artifacts alongside.

    Splitting these is the point: the handle is a function of the facts only,
    while conflicts, history and quarantine still ride on the record.
    """
    canonical = canonicalize({k: v for k, v in state.items() if k not in UNHASHED_KEYS})
    handle = generate_handle(canonical, SCHEMA_VERSION, NORM_VERSION)

    sealed = json.loads(canonical)
    for key in UNHASHED_KEYS:
        value = state.get(key)
        if value not in (None, [], {}):
            sealed[key] = value
    sealed["state_version"] = STATE_VERSION
    canon.assert_no_duplicate_paths(sealed)
    return sealed, handle


def initial_state(extracted: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """The first state in a session — same sealing rules as every later one."""
    state = dict(extracted)
    # the extractor names its quarantine `unmapped`; on a record it is `_unmapped`
    if unmapped := state.pop("unmapped", None):
        state["_unmapped"] = unmapped
    return _seal(state)


def evolve_state(
    old_state: dict[str, Any], new_extracted: dict[str, Any], old_handle: str
) -> tuple[dict[str, Any], str]:
    """Merge new info into old state; return (new_state, new_handle).

    The returned state carries parent_handle = old_handle. The caller
    persists it as a new row; the old record is never touched.
    """
    comparison = compare(old_state, new_extracted)

    new_state = _merge(old_state, new_extracted)
    new_state["conflicts"].extend(comparison.conflicts)

    # a value restated identically is confirmation, not contradiction
    for path in comparison.reinforced:
        new_state["reinforced"][path] = new_state["reinforced"].get(path, 1) + 1

    # a superseded value leaves active state entirely and survives only here,
    # so nothing downstream can read two values for one path
    for record in comparison.conflicts:
        new_state["history"].append({
            "field": record["field"],
            "value": record["old"],
            "superseded_by": record["new"],
            "resolution": record["resolution"],
            "ts": record["timestamp"],
        })

    # Retractions last: a message may state a value and withdraw another in
    # the same breath, and the withdrawal has to win over anything the merge
    # just carried forward.
    for record in _apply_retractions(new_state, new_extracted.get("retractions") or []):
        new_state["history"].append(record)

    sealed, new_handle = _seal(new_state)
    sealed["parent_handle"] = old_handle
    return sealed, new_handle


def _apply_retractions(
    state: dict[str, Any], retractions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Remove withdrawn concepts from active state; return history records.

    "Actually ignore the insurance figure" has to take the field out of active
    state, not merely annotate it. A value that is still live is still sent to
    the model, so a retraction that only logs is not a retraction.
    """
    removed: list[dict[str, Any]] = []
    if not retractions:
        return removed
    now = datetime.now(timezone.utc).isoformat()

    for entry in retractions:
        concept = str(entry.get("concept") or entry.get("raw") or "").strip()
        if not concept:
            continue
        for path in _paths_for_concept(state, concept):
            value = canon.read_path(state, path)
            if value is None:
                continue
            _delete_path(state, path)
            removed.append({
                "field": path, "value": value, "reason": "retracted",
                "resolution": "retracted", "ts": now,
            })
    return removed


def _paths_for_concept(state: dict[str, Any], concept: str) -> list[str]:
    """Every live path a withdrawn concept could name — dynamic or registry."""
    wanted = dyn.content_words(concept)
    if not wanted:
        return []
    found: list[str] = []

    block = state.get(dyn.SECTION) or {}
    for slug in list(block):
        if dyn.words_cover(wanted, dyn.content_words(slug.replace("_", " "))):
            found.extend(canon.leaf_paths_in({slug: block[slug]}, dyn.SECTION))

    # a retraction may also name a registry field ("forget the deadline")
    spec = canon.resolve(concept)
    if spec is not None and canon.read_path(state, spec.path) is not None:
        found.append(spec.path)
    return found


def _delete_path(state: dict[str, Any], path: str) -> None:
    """Remove a dotted path and any container it leaves empty."""
    parts = path.split(".")
    stack: list[tuple[dict[str, Any], str]] = []
    cursor: Any = state
    for part in parts[:-1]:
        if not isinstance(cursor, dict) or part not in cursor:
            return
        stack.append((cursor, part))
        cursor = cursor[part]
    if isinstance(cursor, dict):
        cursor.pop(parts[-1], None)
    for parent, key in reversed(stack):
        if isinstance(parent.get(key), dict) and not parent[key]:
            parent.pop(key, None)
