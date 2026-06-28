"""StateJar FastAPI entry point.

Round 1: health route only. Patent core modules are implemented in Round 2
(see docs/ROUNDS.md). Each module's docstring names the patent claim it satisfies
(see the claim map in docs/ROUND1_SOLUTION.md).
"""
from fastapi import FastAPI

app = FastAPI(title="StateJar", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}