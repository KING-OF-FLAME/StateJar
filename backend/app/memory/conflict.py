"""Conflict detection between an existing state and newly extracted info.

A changed field value is never silently overwritten: the change is
applied, but a conflict record is produced so the divergence stays
auditable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Sections whose fields are compared for value changes.
_TRACKED_SECTIONS = ("facts", "preferences", "decisions", "constraints", "goals")


def detect_conflicts(
    old_state: dict[str, Any], new_extracted: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return conflict records for fields whose value changes.

    Each record: {"field": "section.key", "old": ..., "new": ..., "timestamp": ISO}.
    Fields that are new (absent in old_state) are not conflicts.
    """
    now = datetime.now(timezone.utc).isoformat()
    conflicts: list[dict[str, Any]] = []
    for section in _TRACKED_SECTIONS:
        old_section = old_state.get(section) or {}
        new_section = new_extracted.get(section) or {}
        for key, new_value in new_section.items():
            if key in old_section and old_section[key] != new_value:
                conflicts.append(
                    {
                        "field": f"{section}.{key}",
                        "old": old_section[key],
                        "new": new_value,
                        "timestamp": now,
                    }
                )
    return conflicts
