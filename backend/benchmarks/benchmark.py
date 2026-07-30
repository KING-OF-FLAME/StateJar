"""StateJar benchmark — full-history replay vs. minimal retrieval.

Runs a scripted 30-turn, 3-session conversation through the real StateJar
memory core (extraction → canonicalization → SHA-256 handles → versioning →
minimal retrieval — the same modules the 80-test suite covers; nothing is
reimplemented here) and compares what would be sent to the LLM per turn:

  A) Baseline  — the entire accumulated history replayed on every request
  B) StateJar  — only the minimum retrieved subset + the current message

No LLM is called: only prompt construction is measured, so the benchmark is
free, offline, and deterministic. Token counts use tiktoken (cl100k_base).

Also measured:
  * determinism — canonicalize+hash the same final state 100× with shuffled
    key order → must yield exactly 1 unique handle
  * median canonicalize+hash latency over 100 runs
  * repeated-query consistency — identical retrieved subset both times

Usage:  python benchmarks/benchmark.py
Writes: benchmarks/results.json, benchmarks/results.md, benchmarks/results.csv
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time
from pathlib import Path

import tiktoken

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.llm.gateway import build_system_context  # noqa: E402
from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize  # noqa: E402
from app.memory.extractor import extract_state  # noqa: E402
from app.memory.handle import generate_handle  # noqa: E402
from app.memory.retriever import retrieve_minimum  # noqa: E402
from app.memory.versioning import evolve_state  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent

# OpenRouter pricing for openai/gpt-4o-mini (USD per input token), 2026-07.
MODEL = "openai/gpt-4o-mini"
PRICE_PER_INPUT_TOKEN = 0.15 / 1_000_000

# 30 turns across 3 sessions, instant-demo style: Ayaan's facts → a booking
# in a fresh session (cross-session retrieval) → budget revision + conflict.
# (session, message)
CONVERSATION = [
    # --- session 1: facts land ------------------------------------------------
    ("session-1", "Hi! My name is Ayaan and I live in Mumbai."),
    ("session-1", "I prefer to be contacted by email, never phone calls."),
    ("session-1", "My budget for this delivery is 2000 rupees maximum."),
    ("session-1", "I want the package delivered to my office, not home."),
    ("session-1", "What's my budget again?"),
    ("session-1", "My office is in Bandra Kurla Complex, tower 4."),
    ("session-1", "I decided to go with the express shipping option."),
    ("session-1", "My goal is to get everything delivered before Friday."),
    ("session-1", "Do you remember my name?"),
    ("session-1", "I also prefer eco-friendly packaging when possible."),
    ("session-1", "The delivery date is still unresolved, I need to confirm with my team."),
    ("session-1", "How should you contact me?"),
    # --- session 2: brand-new session, booking from remembered state ---------
    ("session-2", "Book my delivery with my usual preferences."),
    ("session-2", "What's my delivery address?"),
    ("session-2", "I prefer morning deliveries between 9 and 11 am."),
    ("session-2", "My colleague Dhruv might receive it if I'm not there."),
    ("session-2", "Remind me what shipping option I chose?"),
    ("session-2", "I prefer SMS notifications for tracking updates only."),
    ("session-2", "The sender is our vendor in Pune, invoice number 88231."),
    ("session-2", "Is anything still unresolved about my order?"),
    ("session-2", "I want to add a second package going to the same address."),
    ("session-2", "My team confirmed: delivery date is next Wednesday."),
    # --- session 3: budget revision → conflict preserved ----------------------
    ("session-3", "Budget is now 2500 rupees."),
    ("session-3", "What's my full budget situation?"),
    ("session-3", "I prefer paying by UPI, not card."),
    ("session-3", "My company name is Hello World Labs."),
    ("session-3", "Actually make the budget 3000 rupees, final answer."),
    ("session-3", "Were there any conflicting budget changes?"),
    ("session-3", "Book my delivery with my usual preferences."),
    ("session-3", "Summarize everything you know about me."),
]

ENC = tiktoken.get_encoding("cl100k_base")


def ntokens(text: str) -> int:
    return len(ENC.encode(text))


def _shuffled(value, rng: random.Random):
    """Deep-copy `value` with every dict's key order randomly permuted."""
    if isinstance(value, dict):
        keys = list(value.keys())
        rng.shuffle(keys)
        return {k: _shuffled(value[k], rng) for k in keys}
    if isinstance(value, list):
        return [_shuffled(v, rng) for v in value]
    return value


def run_conversation() -> tuple[dict, str, list[dict], int, int]:
    """Drive the 30 turns through the real pipeline; return final state etc."""
    state: dict | None = None
    handle: str | None = None
    baseline_total = 0
    statejar_total = 0
    history: list[str] = []
    per_turn = []

    for i, (session, msg) in enumerate(CONVERSATION, start=1):
        history.append(f"user: {msg}")

        # A) baseline replays the whole accumulated history each turn
        b_tokens = ntokens("\n".join(history))

        # B) StateJar: real ingest (extract → evolve/canonicalize → handle),
        #    then minimal retrieval; cross-session by design — state follows
        #    the user, not the session (module 9).
        extracted = extract_state(msg).model_dump()
        if state is None:
            state = json.loads(canonicalize(extracted))
            handle = generate_handle(canonicalize(extracted), SCHEMA_VERSION, NORM_VERSION)
        else:
            state, handle = evolve_state(state, extracted, handle)
            state.pop("parent_handle", None)

        retrieved = retrieve_minimum(msg, state)
        system_context = build_system_context(handle, retrieved["subset"])
        s_tokens = ntokens(system_context) + ntokens(f"user: {msg}")

        baseline_total += b_tokens
        statejar_total += s_tokens
        per_turn.append(
            {
                "turn": i,
                "session": session,
                "message": msg,
                "baseline_tokens": b_tokens,
                "statejar_tokens": s_tokens,
                "subset_keys": retrieved["metadata"]["subset_keys"],
            }
        )

    return state, handle, per_turn, baseline_total, statejar_total


def run_determinism_checks(state: dict, handle: str) -> dict:
    clean = {k: v for k, v in state.items() if k != "parent_handle"}

    # (a) 100 shuffled-key canonicalizations → must produce 1 unique handle
    rng = random.Random(42)
    handles = set()
    latencies_ms = []
    for _ in range(100):
        shuffled = _shuffled(clean, rng)
        t0 = time.perf_counter()
        h = generate_handle(canonicalize(shuffled), SCHEMA_VERSION, NORM_VERSION)
        latencies_ms.append((time.perf_counter() - t0) * 1000)
        handles.add(h)

    # (c) repeated query → byte-identical subset
    probe = "What's my budget and how should you contact me?"
    s1 = json.dumps(retrieve_minimum(probe, state)["subset"], sort_keys=True)
    s2 = json.dumps(retrieve_minimum(probe, state)["subset"], sort_keys=True)

    return {
        "shuffled_runs": 100,
        "unique_handles": len(handles),
        "matches_live_handle": handles == {handle},
        "median_canonicalize_hash_ms": round(statistics.median(latencies_ms), 3),
        "repeat_query": probe,
        "identical_subset_on_repeat": s1 == s2,
        "passed": len(handles) == 1 and handles == {handle} and s1 == s2,
    }


def main() -> int:
    state, handle, per_turn, baseline_total, statejar_total = run_conversation()
    det = run_determinism_checks(state, handle)

    saved_pct = round(100 * (1 - statejar_total / baseline_total), 1)
    cost_b = baseline_total * PRICE_PER_INPUT_TOKEN
    cost_s = statejar_total * PRICE_PER_INPUT_TOKEN

    results = {
        "model": MODEL,
        "turns": len(CONVERSATION),
        "sessions": len({s for s, _ in CONVERSATION}),
        "baseline_total_tokens": baseline_total,
        "statejar_total_tokens": statejar_total,
        "tokens_saved_pct": saved_pct,
        "mean_context_baseline": round(baseline_total / len(CONVERSATION), 1),
        "mean_context_statejar": round(statejar_total / len(CONVERSATION), 1),
        "cost_baseline_usd": round(cost_b, 6),
        "cost_statejar_usd": round(cost_s, 6),
        "cost_saved_usd": round(cost_b - cost_s, 6),
        "determinism": det,
        "final_handle": handle,
        "per_turn": per_turn,
    }

    (OUT_DIR / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    csv = ["turn,session,baseline_tokens,statejar_tokens"] + [
        f"{t['turn']},{t['session']},{t['baseline_tokens']},{t['statejar_tokens']}"
        for t in per_turn
    ]
    (OUT_DIR / "results.csv").write_text("\n".join(csv) + "\n", encoding="utf-8")

    md = f"""# StateJar Benchmark — Full Replay vs. Minimal Retrieval

Scripted **{results['turns']}-turn, {results['sessions']}-session** conversation
(Ayaan's facts → cross-session booking → budget revision with a preserved
conflict) through the real StateJar memory core — the same extraction,
canonicalization, handle, versioning, and retrieval modules covered by the
80-test suite. No LLM calls: prompt construction only, offline and free.
Token counts: tiktoken `cl100k_base`. Pricing: OpenRouter `{results['model']}`
(${PRICE_PER_INPUT_TOKEN * 1_000_000:.2f} / 1M input tokens).

| Metric | Baseline (full replay) | StateJar (minimal retrieval) |
|---|---|---|
| Total tokens sent ({results['turns']} turns) | {baseline_total:,} | **{statejar_total:,}** |
| Tokens saved | — | **{saved_pct}%** |
| Mean context / turn | {results['mean_context_baseline']:,} tokens | **{results['mean_context_statejar']:,} tokens** |
| Est. input cost | ${results['cost_baseline_usd']:.6f} | **${results['cost_statejar_usd']:.6f}** |
| Est. cost saved | — | **${results['cost_saved_usd']:.6f} ({saved_pct}%)** |

Baseline context grows linearly with the conversation; StateJar stays flat —
the gap widens every turn (per-turn data in `results.csv`, chart-ready).

## Determinism & latency

| Check | Result |
|---|---|
| 100 canonicalize+hash runs, shuffled key order | **{det['unique_handles']}/100 unique handle{'' if det['unique_handles'] == 1 else 's'}** {'✅' if det['unique_handles'] == 1 else '❌'} |
| Shuffled handles match the live pipeline handle | {'✅ PASS' if det['matches_live_handle'] else '❌ FAIL'} |
| Median canonicalize+hash latency | **{det['median_canonicalize_hash_ms']} ms** |
| Repeated query → byte-identical subset | {'✅ PASS' if det['identical_subset_on_repeat'] else '❌ FAIL'} |

Repeat query: *"{det['repeat_query']}"* · Final state handle: `{handle}`

*Generated by `python benchmarks/benchmark.py` — deterministic, no network calls.*
"""
    (OUT_DIR / "results.md").write_text(md, encoding="utf-8")

    print(f"turns / sessions       : {results['turns']} / {results['sessions']}")
    print(f"baseline tokens        : {baseline_total:,}")
    print(f"statejar tokens        : {statejar_total:,}")
    print(f"tokens saved           : {saved_pct}%")
    print(f"mean context per turn  : {results['mean_context_baseline']} vs {results['mean_context_statejar']}")
    print(f"cost saved (est.)      : ${results['cost_saved_usd']:.6f} on {results['model']}")
    print(f"determinism (shuffled) : {det['unique_handles']}/100 unique handles "
          f"{'PASS' if det['unique_handles'] == 1 else 'FAIL'}")
    print(f"median canon+hash      : {det['median_canonicalize_hash_ms']} ms")
    print(f"repeat-query subset    : {'PASS' if det['identical_subset_on_repeat'] else 'FAIL'}")
    print(f"reports written to     : {OUT_DIR}")
    return 0 if det["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
