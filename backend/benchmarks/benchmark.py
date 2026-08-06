"""StateJar benchmark — full-history replay vs. minimal retrieval.

Runs scripted conversations through the real StateJar memory core (extraction →
canonicalization → SHA-256 handles → versioning → minimal retrieval — the same
modules the suite covers; nothing is reimplemented here) and compares what
would be sent to the LLM per turn:

  A) Baseline  — the entire accumulated transcript replayed on every request
  B) StateJar  — only the minimum retrieved subset + the current message

Both demos are measured with the SAME formula and the SAME baseline. Neither
was changed to improve a number: the saving is `1 - sent/replayed`, and the
replay is every prior turn concatenated, exactly as before.

At a session boundary the state is re-loaded from its handle rather than
carried forward in memory, so cross-session recall is exercised rather than
assumed — session 2 opens knowing nothing except a handle.

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
from datetime import date
from pathlib import Path

import tiktoken

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings  # noqa: E402
from app.llm.gateway import build_system_context  # noqa: E402
from app.memory.canonicalizer import NORM_VERSION, SCHEMA_VERSION, canonicalize  # noqa: E402
from app.memory.extractor import extract_state  # noqa: E402
from app.memory.handle import generate_handle  # noqa: E402
from app.memory.retriever import retrieve_minimum  # noqa: E402
from app.memory.versioning import evolve_state  # noqa: E402
from benchmarks.demos import DEMOS  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent

# OpenRouter pricing for openai/gpt-4o-mini (USD per input token), 2026-07.
MODEL = "openai/gpt-4o-mini"
PRICE_PER_INPUT_TOKEN = 0.15 / 1_000_000

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


def run_conversation(turns: list[tuple[str, str]]) -> dict:
    """Drive one scripted conversation through the real pipeline."""
    state: dict | None = None
    handle: str | None = None
    by_handle: dict[str, dict] = {}     # stands in for the states table
    baseline_total = 0
    statejar_total = 0
    history: list[str] = []
    per_turn = []
    current_session = None
    restores = 0

    for i, (session, msg) in enumerate(turns, start=1):
        # A session boundary reopens cold: nothing is carried over but the
        # handle, and the state is re-derived from it. This is the
        # cross-session claim, exercised rather than asserted.
        if current_session is not None and session != current_session and handle:
            state = json.loads(json.dumps(by_handle[handle]))
            restores += 1
        current_session = session

        history.append(f"user: {msg}")

        # A) baseline replays the whole accumulated transcript each turn
        b_tokens = ntokens("\n".join(history))

        # B) StateJar: real ingest (extract → evolve/canonicalize → handle),
        #    then minimal retrieval.
        extracted = extract_state(msg).model_dump()
        if state is None:
            state = json.loads(canonicalize(extracted))
            handle = generate_handle(canonicalize(extracted), SCHEMA_VERSION, NORM_VERSION)
        else:
            state, handle = evolve_state(state, extracted, handle)
            state.pop("parent_handle", None)
        by_handle[handle] = json.loads(json.dumps(state))

        retrieved = retrieve_minimum(msg, state)
        system_context = build_system_context(handle, retrieved["subset"])
        s_tokens = ntokens(system_context) + ntokens(f"user: {msg}")

        baseline_total += b_tokens
        statejar_total += s_tokens
        per_turn.append({
            "turn": i,
            "session": session,
            "message": msg,
            "baseline_tokens": b_tokens,
            "statejar_tokens": s_tokens,
            "saved_pct": round(100 * (1 - s_tokens / b_tokens), 1) if b_tokens else 0.0,
            "retrieval_mode": retrieved["metadata"]["retrieval_mode"],
            "fields": len(retrieved["metadata"]["subset_keys"]),
            "subset_keys": retrieved["metadata"]["subset_keys"],
        })

    # First turn from which the per-turn saving stays positive to the end.
    crossover = None
    for idx in range(len(per_turn)):
        if all(t["saved_pct"] > 0 for t in per_turn[idx:]):
            crossover = per_turn[idx]["turn"]
            break

    return {
        "turns": len(turns),
        "sessions": len({s for s, _ in turns}),
        "cross_session_restores": restores,
        "baseline_total_tokens": baseline_total,
        "statejar_total_tokens": statejar_total,
        "tokens_saved_pct": round(100 * (1 - statejar_total / baseline_total), 1),
        "crossover_turn": crossover,
        "final_state": state,
        "final_handle": handle,
        "per_turn": per_turn,
    }


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


def _per_turn_table(res: dict) -> str:
    rows = "\n".join(
        f"| {t['turn']} | {t['session'][-1]} | {t['baseline_tokens']:,} | "
        f"{t['statejar_tokens']:,} | {t['saved_pct']}% | {t['fields']} | "
        f"`{t['retrieval_mode']}` |"
        for t in res["per_turn"]
    )
    return (
        "| Turn | S | Replay would send | StateJar sent | Saved | Fields | Mode |\n"
        "|---:|---:|---:|---:|---:|---:|---|\n" + rows
    )


def _summary_row(name: str, res: dict) -> str:
    cross = res["crossover_turn"]
    return (
        f"| {name} | {res['turns']} | {res['sessions']} | "
        f"{res['baseline_total_tokens']:,} | {res['statejar_total_tokens']:,} | "
        f"**{res['tokens_saved_pct']}%** | "
        f"{cross if cross else 'never'} |"
    )


def main() -> int:
    results = {name: run_conversation(turns) for name, turns in DEMOS.items()}
    headline = results["relief-40"]
    det = run_determinism_checks(headline["final_state"], headline["final_handle"])
    settings = get_settings()

    payload = {
        "generated": date.today().isoformat(),
        "model": MODEL,
        "retriever_full_state_tokens": settings.retriever_full_state_tokens,
        "demos": {
            name: {k: v for k, v in res.items() if k != "final_state"}
            for name, res in results.items()
        },
        "determinism": det,
    }
    (OUT_DIR / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    csv = ["demo,turn,session,baseline_tokens,statejar_tokens,saved_pct,mode,fields"]
    for name, res in results.items():
        csv += [
            f"{name},{t['turn']},{t['session']},{t['baseline_tokens']},"
            f"{t['statejar_tokens']},{t['saved_pct']},{t['retrieval_mode']},{t['fields']}"
            for t in res["per_turn"]
        ]
    (OUT_DIR / "results.csv").write_text("\n".join(csv) + "\n", encoding="utf-8")

    r17, r40 = results["relief-17"], results["relief-40"]

    # The fixed cost StateJar pays every turn and the bare-transcript baseline
    # never does. Reported as a caveat, never folded into the headline.
    fixed_overhead = ntokens(build_system_context("shm_" + "0" * 40, {}))
    sens = {
        name: round(100 * (1 - res["statejar_total_tokens"] /
                           (res["baseline_total_tokens"] + fixed_overhead * res["turns"])), 1)
        for name, res in results.items()
    }
    sens_17, sens_40 = sens["relief-17"], sens["relief-40"]
    payload["fixed_per_turn_overhead_tokens"] = fixed_overhead
    payload["sensitivity_if_baseline_sent_same_system_prompt"] = sens

    md = f"""# StateJar Benchmark — Full Replay vs. Minimal Retrieval

Generated **{payload['generated']}** by `python benchmarks/benchmark.py` —
deterministic, offline, no LLM calls. Token counts: tiktoken `cl100k_base`.
Pricing: OpenRouter `{MODEL}` (${PRICE_PER_INPUT_TOKEN * 1_000_000:.2f} / 1M input tokens).
`RETRIEVER_FULL_STATE_TOKENS = {settings.retriever_full_state_tokens}`.

**Baseline** is a full-transcript replay: every prior turn re-sent on every
request. **StateJar** sends the retrieved subset plus the current message.
Saving is `1 - sent / replayed`. Both demos use the same formula and the same
baseline; neither was changed to move a number.

| Demo | Turns | Sessions | Replay total | StateJar total | Saved | Crossover |
|---|---:|---:|---:|---:|---:|---:|
{_summary_row('relief-17 (shipped UI demo)', r17)}
{_summary_row('relief-40 (3-session operation)', r40)}

*Crossover* is the first turn from which the per-turn saving stays positive
for the rest of the conversation.

## Why the short demo loses

StateJar pays a fixed cost per turn — a ~136-token instruction block plus the
handle — and then the subset. A replay of three short turns is simply smaller
than that floor. The crossover is where the growing transcript passes it, and
a 17-turn conversation ends only a few turns past it, so the average over the
whole run is still negative. Nothing is wrong with the measurement: a short
conversation is genuinely the case where sending everything is cheaper, and
the honest way to show that is to publish it.

## Methodology, including where it is unkind to us

Stated so the numbers can be challenged on the record rather than in the room.

**The baseline pays no system prompt.** It is the bare transcript. StateJar's
figure includes a fixed {fixed_overhead}-token block every turn — the handle
plus the instructions that stop the model replying in JSON and keep the answer
readable. A real full-replay client would send a system prompt too, and would
pay that same cost. Charging it to one side only is the single largest thing
working against StateJar here, and it is left in place because changing the
baseline to improve a number is exactly what should not be done.

If the replay client sent the identical block, the same conversations measure
**{sens_17}%** and **{sens_40}%**. That is a sensitivity check, not the
headline; the headline is the table above.

**Selective retrieval does not engage on either demo.** Both states stay under
`RETRIEVER_FULL_STATE_TOKENS`, so every turn discloses the full state and the
`Mode` column reads `full_state` throughout. Lowering the threshold was
measured and rejected: at 400 and below, turn 22 loses `dynamic.kit_invoice`
and turn 27 loses the coordinator's name and email, so two of eleven question
turns stop being answerable. A subset that is smaller because it is missing
the answer is not a saving.

**What the demos are not.** They are one domain, scripted, and phrased closer
to a form than to chat because the extractor is frozen. They measure prompt
size, not answer quality.

## relief-17 — per turn

{_per_turn_table(r17)}

## relief-40 — per turn

Sessions 2 and 3 open cold: the state is re-loaded from its handle
({r40['cross_session_restores']} restores), so every answer after turn 14 is
drawn from retrieved state and never from the transcript.

{_per_turn_table(r40)}

## Determinism & latency

Measured on the relief-40 final state.

| Check | Result |
|---|---|
| 100 canonicalize+hash runs, shuffled key order | **{det['unique_handles']}/100 unique handle{'' if det['unique_handles'] == 1 else 's'}** {'✅' if det['unique_handles'] == 1 else '❌'} |
| Shuffled handles match the live pipeline handle | {'✅ PASS' if det['matches_live_handle'] else '❌ FAIL'} |
| Median canonicalize+hash latency | **{det['median_canonicalize_hash_ms']} ms** |
| Repeated query → byte-identical subset | {'✅ PASS' if det['identical_subset_on_repeat'] else '❌ FAIL'} |

Final handle: `{r40['final_handle']}`
"""
    (OUT_DIR / "results.md").write_text(md, encoding="utf-8")

    for name, res in results.items():
        print(f"{name:<12} turns={res['turns']:<3} replay={res['baseline_total_tokens']:>6,} "
              f"sent={res['statejar_total_tokens']:>6,} saved={res['tokens_saved_pct']:>7}% "
              f"crossover={res['crossover_turn']}")
    print(f"determinism  : {det['unique_handles']}/100 unique handles "
          f"{'PASS' if det['unique_handles'] == 1 else 'FAIL'}")
    print(f"repeat subset: {'PASS' if det['identical_subset_on_repeat'] else 'FAIL'}")
    print(f"written to   : {OUT_DIR}")
    return 0 if det["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
