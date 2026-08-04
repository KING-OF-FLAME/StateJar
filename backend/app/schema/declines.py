"""Every reason StateJar can give for not storing something, in one place.

A user who is shown `low_confidence` and nothing else has been told that the
system declined, but not why — which is the exact failure the declined section
exists to prevent. So each reason code here is required to have a help entry
explaining it in plain language, and `tests/test_help_coverage.py` fails the
build if one is missing.

This module is deliberately **inert**. Nothing in the extraction path imports
it, and adding a code here does not change what any guard does. It is a
declaration of what the guards are known to emit, and the coverage test keeps
the declaration honest by reading the guards' own source: a new reason literal
introduced in `extractor.py`, `dynamic.py`, `canonical.py` or `rules.py` fails
the test until it is listed here *and* documented.

Two families, kept apart because they mean different things to a user:

  quarantine  the value was rejected and parked in `_unmapped`. Something was
              said, and StateJar refused to store it.
  unresolved  a field was named but no value was given. Nothing was rejected;
              there was nothing to store yet.

A third entry covers the one reason that is a template rather than a fixed
string — a recorded contradiction names the two values involved.
"""

from __future__ import annotations

from typing import Literal

QUARANTINE = "quarantine"
UNRESOLVED = "unresolved"
CONFLICT = "conflict"

Family = Literal["quarantine", "unresolved", "conflict"]

# reason string as emitted -> (family, whether it is an f-string template)
REASONS: dict[str, tuple[Family, bool]] = {
    # --- quarantine: a value was refused ---------------------------------
    # the registry has no field by that name and no alias resolves it
    "unknown_key": (QUARANTINE, False),
    # the tier that proposed it was less sure than the field demands
    "low_confidence": (QUARANTINE, False),
    # the field exists, but its normalizer would not accept this value
    "rejected_value": (QUARANTINE, False),
    # the clause was a question, a negation or a retraction, not a claim
    "not an assertion": (QUARANTINE, False),
    # --- unresolved: a field was named without a value --------------------
    "not provided": (UNRESOLVED, False),
    "user unsure": (UNRESOLVED, False),
    "pending": (UNRESOLVED, False),
    # --- conflict: recorded, not declined ---------------------------------
    # emitted as f"user rejected {a} in favour of {b}"
    "user rejected": (CONFLICT, True),
}


def slug(reason: str) -> str:
    """Stable id fragment for a reason: `not an assertion` -> `not_an_assertion`."""
    return "_".join(reason.lower().split())


def help_id(reason: str) -> str:
    """The help entry a reason must have. Matches the ids under `decline.*`."""
    return f"decline.{slug(reason)}"


def family(reason: str) -> Family | None:
    entry = REASONS.get(reason)
    return entry[0] if entry else None


TEMPLATES: tuple[str, ...] = tuple(r for r, (_, t) in REASONS.items() if t)

__all__ = [
    "REASONS", "TEMPLATES", "QUARANTINE", "UNRESOLVED", "CONFLICT",
    "slug", "help_id", "family",
]
