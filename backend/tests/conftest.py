"""Ensure the backend root (containing the `app` package) is importable."""

import sys
from collections.abc import Generator
from pathlib import Path

import pytest

BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.config import get_settings  # noqa: E402 — needs the path above


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
