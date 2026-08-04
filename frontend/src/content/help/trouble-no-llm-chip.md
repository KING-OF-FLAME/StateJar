---
id: trouble.no-llm-chip
title: No LLM chip appears
category: troubleshooting
updated_at: 2026-08-04
summary: You expected [tier 3](#tier.llm) to run and there is no `llm` chip — only `rules`.
keywords: llm chip missing tier3 not running gpt extraction
---

**Symptom.** You expected [tier 3](#tier.llm) to run and there is no `llm` chip — only `rules`.

**Likely cause.** A skipped tier shows no chip at all. Tier 3 is gated behind several
conditions and all of them must hold: [`EXTRACTOR_LLM_FALLBACK`](#settings.extractor_llm_fallback)
must be `true`, a provider key must be saved for **the account making the
call**, and the message must actually look like it needs tier 3 — at least 12
words with at most 2 fields found by the cheap tiers, or long and sparse, or
over five words with nothing extracted at all.

The most common cause by far is the second one: a fresh account with no
provider key. The second most common is the third: the message was short and
clean, so the cheap tiers answered it completely and tier 3 was correctly not
needed.

**Fix.** Check `EXTRACTOR_LLM_FALLBACK=true` on the deployment, save a provider
key for the account you are testing with, and try a genuinely messy message —
a rambling sentence with a value buried in a subordinate clause. If the tier
runs and fails you will get an amber chip, which is a different and more
informative outcome than no chip.
