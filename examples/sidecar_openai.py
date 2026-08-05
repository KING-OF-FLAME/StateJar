"""StateJar as a sidecar: your LLM, your key, StateJar's memory.

Three calls per turn, in this order:

    1. POST /memory/ingest   the user's message -> extracted, hashed, stored
    2. POST /memory/query    the minimum-sufficient context for this question
    3. your own LLM call     with `memory_context` as the system message

Order is the whole point and it is not an accident. Ingest **commits before**
retrieve runs, so the context handed to your model already contains the turn
the user just sent. Reversing them, or moving ingest to a background task,
means a question that depends on the message that asked it retrieves state
from before that message existed -- and the failure is invisible, because you
still get a fluent answer, just one built on stale memory. On a product whose
claim is determinism that is the one trade not worth making.

StateJar never sees your provider key and never stores the transcript: it is
handed one message at a time, extracts the facts, and keeps only those.

Run it:

    pip install openai requests
    export STATEJAR_API_KEY=sj_...          # API Keys page in the console
    export OPENAI_API_KEY=sk-...            # your own key, never sent to us
    python examples/sidecar_openai.py

Against a local instance, set STATEJAR_BASE=http://localhost:8000/api/v1.
"""

from __future__ import annotations

import os
import sys

import requests

BASE = os.environ.get("STATEJAR_BASE", "https://api.statejar.com/api/v1")
SESSION = os.environ.get("STATEJAR_SESSION", "sidecar-demo")

try:
    SJ_KEY = os.environ["STATEJAR_API_KEY"]
except KeyError:
    sys.exit("set STATEJAR_API_KEY (create one on the API Keys page)")

HEADERS = {"X-API-Key": SJ_KEY, "Content-Type": "application/json"}


def ingest(text: str) -> dict:
    """Step 1. Returns the new handle and what was stored or declined."""
    r = requests.post(f"{BASE}/memory/ingest", headers=HEADERS,
                      json={"session_tag": SESSION, "text": text}, timeout=60)
    r.raise_for_status()
    return r.json()


def recall(question: str) -> dict:
    """Step 2. `memory_context` is prompt-ready; `subset` is the same thing as
    data, if you would rather format it yourself."""
    r = requests.post(f"{BASE}/memory/query", headers=HEADERS,
                      json={"session_tag": SESSION, "query": question,
                            "audit": True}, timeout=60)
    r.raise_for_status()
    return r.json()


def answer(question: str, memory_context: str) -> str:
    """Step 3. Your provider, your key, your client. StateJar is not in it."""
    from openai import OpenAI

    client = OpenAI()          # reads OPENAI_API_KEY
    reply = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": memory_context},
            {"role": "user", "content": question},
        ],
    )
    return reply.choices[0].message.content


def turn(text: str, *, ask: bool = True) -> None:
    stored = ingest(text)
    declined = stored["state"].get("_unmapped") or {}
    print(f"\n> {text}")
    print(f"  handle    {stored['handle']}")
    print(f"  tiers     {stored.get('extraction_tiers')}")
    if declined:
        print(f"  declined  {[(k, v.get('reason')) for k, v in declined.items()]}")
    if not ask:
        return
    got = recall(text)
    print(f"  disclosed {got['metadata']['subset_keys']}   (audit {got['audit_id']})")
    print(f"  answer    {answer(text, got['memory_context'])}")


if __name__ == "__main__":
    # Statements first, then a question that can only be answered from what the
    # earlier turns established -- which is the thing worth checking.
    turn("My name is Meera Nair and I'm from Pune", ask=False)
    turn("Budget is under 25000 and the deadline is 20 September", ask=False)
    turn("What's my budget, and remind me when it's due?")
