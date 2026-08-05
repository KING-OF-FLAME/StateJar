"""Aggregates behind the dashboard charts.

Pure functions over rows the caller has already scoped to one account, so the
shaping is testable without a database and the scoping cannot be forgotten in
here — there is no user id to filter on, because the rows arriving are already
the caller's own.

Three questions, because those are the three the product can answer that a
transcript-shaped memory cannot:

  namespaces  how many fields are live versus superseded, per section. This is
              "one field, one value" made countable: a superseded value left
              active state entirely and survives only in `history`.
  declines    what was refused, by reason, over time. `_unmapped` accumulates
              across a session's versions, so a decline is attributed to the
              version where it FIRST appears — counting the block as it stands
              on each version would report the same refusal once per later
              turn and turn a flat line into a rising one.
  lineage     the chain of handles per session, which is the append-only claim
              made visible.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from app.schema import canonical as canon

# A decline with no stated reason is still a decline; it groups under this
# rather than being dropped, because a silent refusal is the thing the product
# exists to not do.
UNSTATED = "unstated"


def _section_of(path: Any) -> str:
    """The namespace a dotted field path belongs to."""
    head = str(path or "").split(".", 1)[0]
    return head if head in canon.ACTIVE_SECTIONS else "other"


def _active_by_section(state: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for section in canon.ACTIVE_SECTIONS:
        block = state.get(section)
        n = sum(1 for _ in canon.leaf_paths_in(block, section))
        if n:
            counts[section] = n
    return counts


def _superseded_by_section(state: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in state.get("history") or []:
        if not isinstance(record, dict):
            continue
        section = _section_of(record.get("field"))
        counts[section] = counts.get(section, 0) + 1
    return counts


def _declines_in(state: Mapping[str, Any]) -> dict[str, str]:
    """Every refusal on this state, as `key -> reason`.

    Quarantine and unresolved are both refusals — one is "the value was not
    admissible", the other "no value was given" — and a user asking "what did
    it decline?" means both.
    """
    out: dict[str, str] = {}
    for key, entry in (state.get("_unmapped") or {}).items():
        reason = entry.get("reason") if isinstance(entry, dict) else None
        out[f"_unmapped.{key}"] = str(reason or UNSTATED)
    for entry in state.get("unresolved") or []:
        if isinstance(entry, dict) and entry.get("field"):
            out[f"unresolved.{entry['field']}"] = str(entry.get("reason") or UNSTATED)
    return out


def summarize(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Shape one account's state rows into the three chart payloads.

    `rows` must be ordered oldest first and carry `session_tag`, `handle`,
    `created_at` (already an ISO string) and `state_json`.
    """
    by_session: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_session.setdefault(str(row.get("session_tag") or ""), []).append(row)

    active: dict[str, int] = {}
    superseded: dict[str, int] = {}
    buckets: dict[str, dict[str, int]] = {}
    reason_totals: dict[str, int] = {}
    lineage: list[dict[str, Any]] = []
    state_count = 0

    for tag, versions in by_session.items():
        state_count += len(versions)
        seen: set[str] = set()
        chain: list[dict[str, Any]] = []

        for index, row in enumerate(versions, start=1):
            state = row.get("state_json")
            if not isinstance(state, dict):
                continue
            created = str(row.get("created_at") or "")

            # a decline is counted on the version that introduced it
            fresh = {k: v for k, v in _declines_in(state).items() if k not in seen}
            seen.update(fresh)
            if fresh:
                day = created[:10] or "unknown"
                bucket = buckets.setdefault(day, {})
                for reason in fresh.values():
                    bucket[reason] = bucket.get(reason, 0) + 1
                    reason_totals[reason] = reason_totals.get(reason, 0) + 1

            chain.append({
                "handle": row.get("handle"),
                "version": index,
                "created_at": created,
                "fields": sum(_active_by_section(state).values()),
                "declines": len(fresh),
            })

            if index == len(versions):      # the live state for this session
                for section, n in _active_by_section(state).items():
                    active[section] = active.get(section, 0) + n
                for section, n in _superseded_by_section(state).items():
                    superseded[section] = superseded.get(section, 0) + n

        if chain:
            lineage.append({"session_tag": tag, "versions": chain})

    namespaces = [
        {"namespace": s, "active": active.get(s, 0), "superseded": superseded.get(s, 0)}
        for s in sorted(set(active) | set(superseded),
                        key=lambda s: -(active.get(s, 0) + superseded.get(s, 0)))
    ]
    ordered_days = sorted(buckets)
    lineage.sort(key=lambda e: e["session_tag"])

    return {
        "namespaces": namespaces,
        "declines": {
            # most common first, so the chart's series order is stable and the
            # front end can fold the tail into "Other" without re-ranking
            "reasons": sorted(reason_totals, key=lambda r: (-reason_totals[r], r)),
            "totals": reason_totals,
            "buckets": [{"date": d, "counts": buckets[d]} for d in ordered_days],
        },
        "lineage": lineage,
        "totals": {
            "sessions": len(lineage),
            "states": state_count,
            "active": sum(active.values()),
            "superseded": sum(superseded.values()),
            "declined": sum(reason_totals.values()),
        },
    }
