"""Ensure the backend root (containing the `app` package) is importable."""

import sys
from collections.abc import Generator
from pathlib import Path

import pytest

BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.config import get_settings  # noqa: E402 — needs the path above
from app.security import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def _deterministic_pipeline(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Pin the optional ML layers off for the whole suite.

    Both default to running whenever their package is importable, so without
    this a developer with requirements-ml.txt installed would get different
    extraction (and therefore different handles) than CI does. Tests that
    exercise those layers switch them on explicitly with a mocked model.
    """
    monkeypatch.setenv("EXTRACTOR_MODE", "rules")
    monkeypatch.setenv("RETRIEVER_SEMANTIC", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_rate_limits() -> Generator[None, None, None]:
    """Suites that log in repeatedly must not throttle each other.

    Left off by default and switched on explicitly by the rate-limit tests,
    which also reset the shared in-process counters.
    """
    limiter.enabled = False
    yield
    limiter.enabled = False


# --- fake credentials for tests ----------------------------------------------
# Built by concatenation so no secret scanner ever matches the source. Real
# provider keys must never appear in this repository, not even as fixtures:
# a scanner cannot tell a fixture from a live credential, and neither can a
# reviewer skimming a diff.
_FAKE_PREFIX = "test-" + "not-a-real-key-"


def fake_key(label: str = "0000") -> str:
    """A unique, obviously-fake provider key for tests."""
    return _FAKE_PREFIX + label


FAKE_PROVIDER_KEY = fake_key("0000")
