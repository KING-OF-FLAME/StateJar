"""Ensure the backend root (containing the `app` package) is importable."""

import sys
from pathlib import Path

BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)
