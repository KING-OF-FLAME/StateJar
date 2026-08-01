"""Unambiguous timestamps on the wire.

Every `created_at` is written as `datetime.now(timezone.utc)`, but the
DateTime columns are naive, so the driver hands the value back with its
tzinfo stripped. Calling `.isoformat()` on that produces a string with no
offset — which `new Date(...)` in a browser reads as *local* time, putting
every timestamp out by the viewer's UTC offset (an entry created a moment
ago rendered as "6h ago" from IST).

Naive values are therefore stamped as UTC, which is what they always were.
"""

from __future__ import annotations

from datetime import datetime, timezone


def iso_utc(value: datetime | None) -> str | None:
    """ISO 8601 with an explicit offset, or None."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
