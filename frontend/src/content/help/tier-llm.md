---
id: tier.llm
title: Tier 3: LLM extraction
category: reference
updated_at: 2026-08-04
summary: Strict-JSON extraction via your own key, on messy input only.
keywords: llm tier3 gpt extraction json fallback gated
---

**What it is.** A language model asked to return strict JSON for a message the
cheap tiers could not resolve. It uses **your** provider key.

**Why it is gated.** It costs money and latency on every call, so it fires only
when the message looks like it needs it. The trigger conditions are all of:

- [`EXTRACTOR_LLM_FALLBACK`](#settings.extractor_llm_fallback) is on
- a provider key is saved for the account
- the message is at least 12 words, **and** the cheap tiers found at most 2
  fields — or the message is long and sparse (about one field per six words),
  or it is over five words and produced nothing at all

**Confidence.** 0.5, the lowest of the three.

**When it fails.** The [fallback chain](#settings.extractor_llm_fallback_models)
is tried first. If everything fails, the tier is marked *unavailable* and shows
an amber [chip](#ui.tier_chips) — attempted and did not answer, which is not the
same as skipped.

**What it cannot do.** It cannot bypass a guard. Its output is type-checked and
routed exactly like a rule's. This is why probabilistic extraction is safe here
at all: extraction runs *before* canonicalization, so the model proposes and the
deterministic layer disposes.

Not seeing the chip when you expected it? See
[no LLM chip appearing](#trouble.no-llm-chip).
