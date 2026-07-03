"""Canonicalization of StructuredState for StateJar.

Converts a structured-state dict into a deterministic canonical JSON
string: identical meaning always yields byte-identical output. This is
the basis for content-addressed state handles.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "v1"
NORM_VERSION = "v1"

# Values of these fields are enum-like and are lowercased.
_ENUM_VALUES = {"email", "call", "whatsapp"}

# "₹2,000" / "Rs 2000" / "INR 2,000" / "2000" → numeric
_NUMERIC_RE = re.compile(r"^\s*(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*$", re.IGNORECASE)

# Date formats accepted for ISO 8601 normalization.
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
    "%b %d %Y",
)


def _normalize_number(value: str) -> int | float | None:
    """Parse a currency/number-like string; return None if not numeric."""
    m = _NUMERIC_RE.match(value)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    if "." in raw:
        f = float(raw)
        return int(f) if f.is_integer() else f
    return int(raw)


def _normalize_date(value: str) -> str | None:
    """Parse a date-like string into ISO 8601 (YYYY-MM-DD); None if not a date."""
    stripped = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _normalize_string(value: str) -> Any:
    """Apply whitespace, enum, number, and date normalization to a string."""
    collapsed = re.sub(r"\s+", " ", value).strip()
    if collapsed.lower() in _ENUM_VALUES:
        return collapsed.lower()
    number = _normalize_number(collapsed)
    if number is not None:
        return number
    date = _normalize_date(collapsed)
    if date is not None:
        return date
    return collapsed


def _normalize(value: Any) -> Any:
    """Recursively normalize a value; returns None for empty containers/nulls."""
    if isinstance(value, str):
        result = _normalize_string(value)
        return result if result != "" else None
    if isinstance(value, dict):
        out = {}
        for key in sorted(value):
            norm = _normalize(value[key])
            if norm is not None:
                out[str(key)] = norm
        return out or None
    if isinstance(value, (list, tuple)):
        items = [n for n in (_normalize(v) for v in value) if n is not None]
        return items or None
    if isinstance(value, bool) or value is None:
        return value if value is not None else None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def canonicalize(state: dict[str, Any]) -> str:
    """Return the canonical JSON string for a structured-state dict.

    Keys are sorted recursively, strings/numbers/dates normalized, empty
    values dropped, and schema/norm versions attached.
    """
    normalized = _normalize(state) or {}
    normalized["schema_version"] = SCHEMA_VERSION
    normalized["norm_version"] = NORM_VERSION
    return json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
