"""The git commit this process is running.

Surfaced on /api/v1/health so a deployed instance can be compared against
local main without guessing — "is prod actually running what I pushed?"
answered by reading one field.

Resolution order, first hit wins:
  1. GIT_SHA            explicit override (any host)
  2. RAILWAY_GIT_COMMIT_SHA / VERCEL_GIT_COMMIT_SHA / SOURCE_VERSION
                        injected by the platform at build time
  3. `git rev-parse`    local development, where a checkout exists
  4. "unknown"          a container with neither env nor .git
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

_SHA_ENV_VARS = (
    "GIT_SHA",
    "RAILWAY_GIT_COMMIT_SHA",
    "VERCEL_GIT_COMMIT_SHA",
    "SOURCE_VERSION",  # Heroku-style
)

SHORT_SHA_LEN = 7


@lru_cache
def git_sha() -> str:
    """Short commit sha for this build, or "unknown"."""
    for name in _SHA_ENV_VARS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value[:SHORT_SHA_LEN]

    try:
        # never let a missing git binary or a non-repo directory break /health
        result = subprocess.run(
            ["git", "rev-parse", f"--short={SHORT_SHA_LEN}", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:  # noqa: BLE001 — health must answer regardless
        pass
    return "unknown"
