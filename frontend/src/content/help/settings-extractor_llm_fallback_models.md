---
id: settings.extractor_llm_fallback_models
title: EXTRACTOR_LLM_FALLBACK_MODELS
category: settings
updated_at: 2026-08-04
summary: Environment variable EXTRACTOR_LLM_FALLBACK_MODELS. Default: openrouter/anthropic/claude-3.5-haiku,openai/gpt-4o-mini
keywords: fallback models chain retry llm
---

**Environment variable:** `EXTRACTOR_LLM_FALLBACK_MODELS`

**Default:** `openrouter/anthropic/claude-3.5-haiku,openai/gpt-4o-mini`


Comma-separated models to try, in order, when
[`EXTRACTOR_LLM_MODEL`](#settings.extractor_llm_model) fails.

A rate limit or an outage on one vendor should degrade extraction quality, not
stop it. The chain is tried in order; if every model fails, the tier is marked
**unavailable** and you see the amber chip — the deterministic tiers still ran,
and the state is still valid, just thinner.

Only recoverable failures advance the chain. A bug in StateJar's own code is
not retried against another vendor; it is raised.
