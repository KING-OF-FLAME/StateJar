# StateJar Benchmark — Full Replay vs. Minimal Retrieval

Generated **2026-08-06** by `python benchmarks/benchmark.py` —
deterministic, offline, no LLM calls. Token counts: tiktoken `cl100k_base`.
Pricing: OpenRouter `openai/gpt-4o-mini` ($0.15 / 1M input tokens).
`RETRIEVER_FULL_STATE_TOKENS = 800`.

**Baseline** is a full-transcript replay: every prior turn re-sent on every
request. **StateJar** sends the retrieved subset plus the current message.
Saving is `1 - sent / replayed`. Both demos use the same formula and the same
baseline; neither was changed to move a number.

| Demo | Turns | Sessions | Replay total | StateJar total | Saved | Crossover |
|---|---:|---:|---:|---:|---:|---:|
| relief-17 (shipped UI demo) | 17 | 1 | 2,169 | 5,137 | **-136.8%** | never |
| relief-40 (3-session operation) | 40 | 3 | 9,955 | 14,616 | **-46.8%** | never |

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
figure includes a fixed 152-token block every turn — the handle
plus the instructions that stop the model replying in JSON and keep the answer
readable. A real full-replay client would send a system prompt too, and would
pay that same cost. Charging it to one side only is the single largest thing
working against StateJar here, and it is left in place because changing the
baseline to improve a number is exactly what should not be done.

If the replay client sent the identical block, the same conversations measure
**-8.1%** and **8.8%**. That is a sensitivity check, not the
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

| Turn | S | Replay would send | StateJar sent | Saved | Fields | Mode |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 1 | 19 | 192 | -910.5% | 1 | `full_state` |
| 2 | 1 | 35 | 208 | -494.3% | 3 | `full_state` |
| 3 | 1 | 46 | 242 | -426.1% | 5 | `full_state` |
| 4 | 1 | 64 | 264 | -312.5% | 7 | `full_state` |
| 5 | 1 | 78 | 274 | -251.3% | 8 | `full_state` |
| 6 | 1 | 96 | 299 | -211.5% | 10 | `full_state` |
| 7 | 1 | 108 | 301 | -178.7% | 11 | `full_state` |
| 8 | 1 | 119 | 305 | -156.3% | 11 | `full_state` |
| 9 | 1 | 128 | 310 | -142.2% | 12 | `full_state` |
| 10 | 1 | 137 | 316 | -130.7% | 13 | `full_state` |
| 11 | 1 | 151 | 314 | -107.9% | 12 | `full_state` |
| 12 | 1 | 170 | 343 | -101.8% | 14 | `full_state` |
| 13 | 1 | 183 | 331 | -80.9% | 14 | `full_state` |
| 14 | 1 | 193 | 353 | -82.9% | 15 | `full_state` |
| 15 | 1 | 204 | 359 | -76.0% | 16 | `full_state` |
| 16 | 1 | 212 | 360 | -69.8% | 17 | `full_state` |
| 17 | 1 | 226 | 366 | -61.9% | 17 | `full_state` |

## relief-40 — per turn

Sessions 2 and 3 open cold: the state is re-loaded from its handle
(2 restores), so every answer after turn 14 is
drawn from retrieved state and never from the transcript.

| Turn | S | Replay would send | StateJar sent | Saved | Fields | Mode |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 1 | 19 | 192 | -910.5% | 1 | `full_state` |
| 2 | 1 | 37 | 206 | -456.8% | 3 | `full_state` |
| 3 | 1 | 51 | 214 | -319.6% | 4 | `full_state` |
| 4 | 1 | 67 | 239 | -256.7% | 6 | `full_state` |
| 5 | 1 | 85 | 260 | -205.9% | 8 | `full_state` |
| 6 | 1 | 96 | 291 | -203.1% | 10 | `full_state` |
| 7 | 1 | 105 | 289 | -175.2% | 10 | `full_state` |
| 8 | 1 | 117 | 301 | -157.3% | 11 | `full_state` |
| 9 | 1 | 128 | 311 | -143.0% | 12 | `full_state` |
| 10 | 1 | 137 | 324 | -136.5% | 13 | `full_state` |
| 11 | 1 | 148 | 324 | -118.9% | 13 | `full_state` |
| 12 | 1 | 158 | 323 | -104.4% | 13 | `full_state` |
| 13 | 1 | 167 | 329 | -97.0% | 14 | `full_state` |
| 14 | 1 | 175 | 338 | -93.1% | 15 | `full_state` |
| 15 | 2 | 194 | 368 | -89.7% | 17 | `full_state` |
| 16 | 2 | 202 | 357 | -76.7% | 17 | `full_state` |
| 17 | 2 | 212 | 374 | -76.4% | 18 | `full_state` |
| 18 | 2 | 226 | 366 | -61.9% | 17 | `full_state` |
| 19 | 2 | 236 | 362 | -53.4% | 17 | `full_state` |
| 20 | 2 | 247 | 378 | -53.0% | 18 | `full_state` |
| 21 | 2 | 257 | 383 | -49.0% | 19 | `full_state` |
| 22 | 2 | 271 | 387 | -42.8% | 19 | `full_state` |
| 23 | 2 | 279 | 387 | -38.7% | 20 | `full_state` |
| 24 | 2 | 292 | 392 | -34.2% | 20 | `full_state` |
| 25 | 2 | 300 | 387 | -29.0% | 20 | `full_state` |
| 26 | 2 | 309 | 402 | -30.1% | 21 | `full_state` |
| 27 | 2 | 322 | 406 | -26.1% | 21 | `full_state` |
| 28 | 3 | 332 | 407 | -22.6% | 22 | `full_state` |
| 29 | 3 | 343 | 408 | -19.0% | 22 | `full_state` |
| 30 | 3 | 355 | 427 | -20.3% | 23 | `full_state` |
| 31 | 3 | 364 | 426 | -17.0% | 24 | `full_state` |
| 32 | 3 | 372 | 425 | -14.2% | 24 | `full_state` |
| 33 | 3 | 381 | 440 | -15.5% | 25 | `full_state` |
| 34 | 3 | 392 | 452 | -15.3% | 26 | `full_state` |
| 35 | 3 | 404 | 453 | -12.1% | 26 | `full_state` |
| 36 | 3 | 415 | 449 | -8.2% | 26 | `full_state` |
| 37 | 3 | 426 | 460 | -8.0% | 27 | `full_state` |
| 38 | 3 | 433 | 456 | -5.3% | 27 | `full_state` |
| 39 | 3 | 443 | 459 | -3.6% | 27 | `full_state` |
| 40 | 3 | 458 | 464 | -1.3% | 27 | `full_state` |

## Determinism & latency

Measured on the relief-40 final state.

| Check | Result |
|---|---|
| 100 canonicalize+hash runs, shuffled key order | **1/100 unique handle** ✅ |
| Shuffled handles match the live pipeline handle | ❌ FAIL |
| Median canonicalize+hash latency | **12.166 ms** |
| Repeated query → byte-identical subset | ✅ PASS |

Final handle: `shm_609e5524c00cb017531995fbc27c016a5fcdbe04`
