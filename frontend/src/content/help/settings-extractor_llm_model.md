---
id: settings.extractor_llm_model
title: EXTRACTOR_LLM_MODEL
category: settings
updated_at: 2026-08-04
summary: Environment variable EXTRACTOR_LLM_MODEL. Default: openrouter/openai/gpt-4o-mini
keywords: llm model extraction tier3 json
---

**Environment variable:** `EXTRACTOR_LLM_MODEL`

**Default:** `openrouter/openai/gpt-4o-mini`


Which model [tier 3](#tier.llm) asks first.

It must be a model that reliably returns strict JSON — extraction is a
structured task, and a model that editorialises around its JSON fails the parse
and burns the call. `gpt-4o-mini` is the default because it is cheap and
consistent at exactly this.

The id is namespaced with its provider, because a bare `openai/gpt-4o-mini` is
ambiguous between an OpenRouter id and an OpenAI routing prefix.
