"""Deterministic state-handle generation for StateJar.

A handle is a content address: SHA-256 over the canonical state string
plus the schema/normalization versions, prefixed with "shm_".
"""

from __future__ import annotations

import hashlib
import hmac

HANDLE_PREFIX = "shm_"
_HEX_CHARS = 40


def generate_handle(
    canonical_state: str, schema_version: str, norm_version: str
) -> str:
    """Derive the deterministic handle for a canonical state string."""
    digest = hashlib.sha256(
        f"{canonical_state}|{schema_version}|{norm_version}".encode("utf-8")
    ).hexdigest()
    return HANDLE_PREFIX + digest[:_HEX_CHARS]


def verify_handle(
    canonical_state: str, schema_version: str, norm_version: str, handle: str
) -> bool:
    """Check that a handle matches the given canonical state and versions."""
    expected = generate_handle(canonical_state, schema_version, norm_version)
    return hmac.compare_digest(expected, handle)
