"""Conflict detection between an existing state and newly extracted info.

A changed field value is never silently overwritten: the change is applied,
but a conflict record is produced so the divergence stays auditable.

The comparison happens on **normalized** values, not on the strings the user
typed. Comparing surface forms flagged "15 Aug" against "15 August" as a
contradiction — the same date, restated. That is not a conflict; it is the
user confirming something, and treating it as a conflict both filled the audit
log with noise and made the resolution order matter for a value that never
actually changed.

Restating a value now increments `reinforced_count` instead. A genuine
disagreement resolves latest-wins and moves the superseded value to
`history[]`, so active state is left holding exactly one value per path.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any

from app.schema import canonical as canon

# Sections whose fields are compared for value changes.
_TRACKED_SECTIONS = canon.ACTIVE_SECTIONS

LATEST_WINS = "latest_wins"


@dataclass
class Comparison:
    """What a new extraction does to the state it lands on."""

    conflicts: list[dict[str, Any]] = dc_field(default_factory=list)
    reinforced: list[str] = dc_field(default_factory=list)


# Keys on a stored value that describe how it was said rather than what it
# says. Two spellings of one measurement differ here and nowhere else, so
# comparing them would report a contradiction where the user merely repeated
# themselves in different words.
_PRESENTATION_KEYS = ("raw", "concept")


def _identity(value: Any) -> Any:
    """The part of a value that decides whether it changed."""
    if isinstance(value, dict) and any(k in value for k in ("type", "iso", "value")):
        return {k: v for k, v in value.items() if k not in _PRESENTATION_KEYS}
    return value


def _normalized(path: str, value: Any) -> Any:
    """The value as its field defines it, for comparison only.

    Values already written through `canonicalize()` are normalized, so this is
    a no-op for them. It matters for state written before this layer existed,
    where `deadline` may still hold the raw string "15 Aug".
    """
    spec = canon.resolve(path)
    if spec is None:
        # a dynamic field: already normalized on write, so only the
        # presentation keys need stripping
        return _identity(value)
    try:
        normalized = spec.normalizer(value)
    except (TypeError, ValueError):
        return value
    if normalized in (None, "", [], {}):
        return value
    # a date compares on its ISO day; `raw` deliberately differs by definition
    if spec.type == "date" and isinstance(normalized, dict):
        return normalized.get("iso")
    return normalized


def compare(
    old_state: dict[str, Any], new_extracted: dict[str, Any]
) -> Comparison:
    """Classify every incoming field as new, reinforcing, or conflicting."""
    now = datetime.now(timezone.utc).isoformat()
    result = Comparison()

    for section in _TRACKED_SECTIONS:
        for path in canon.leaf_paths_in(new_extracted.get(section), section):
            new_value = canon.read_path(new_extracted, path)
            old_value = canon.read_path(old_state, path)
            if old_value is None:
                continue  # a field we did not have is information, not conflict
            if isinstance(old_value, list) and isinstance(new_value, list):
                continue  # lists accumulate; growth is not contradiction

            if _normalized(path, old_value) == _normalized(path, new_value):
                result.reinforced.append(path)
                continue

            result.conflicts.append({
                "field": path,
                "old": old_value,
                "new": new_value,
                "resolution": LATEST_WINS,
                "timestamp": now,
            })
    return result


def detect_conflicts(
    old_state: dict[str, Any], new_extracted: dict[str, Any]
) -> list[dict[str, Any]]:
    """Conflict records only. Kept as the public shape callers already use."""
    return compare(old_state, new_extracted).conflicts
