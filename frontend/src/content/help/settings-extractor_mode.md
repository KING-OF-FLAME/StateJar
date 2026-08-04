---
id: settings.extractor_mode
title: EXTRACTOR_MODE
category: settings
updated_at: 2026-08-04
summary: Environment variable EXTRACTOR_MODE. Default: auto
keywords: extractor mode tiers rules gliner auto
---

**Environment variable:** `EXTRACTOR_MODE`

**Default:** `auto`


Which extraction tiers may run.

| Value | Behaviour |
|---|---|
| `auto` | rules, then [GLiNER2](#tier.gliner2) if its dependencies are installed |
| `gliner` | force the neural tier on; fail loudly if it cannot load |
| `rules` | [deterministic patterns](#tier.rules) only |

`rules` is the fastest and the most predictable, and it is what the test suite
runs with. It is also a reasonable production setting if your input is
well-formed — the neural tier costs memory and start-up time.

This does **not** control [tier 3](#tier.llm); that is
[`EXTRACTOR_LLM_FALLBACK`](#settings.extractor_llm_fallback).
