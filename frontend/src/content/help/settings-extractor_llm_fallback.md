---
id: settings.extractor_llm_fallback
title: EXTRACTOR_LLM_FALLBACK
category: settings
updated_at: 2026-08-04
summary: Environment variable EXTRACTOR_LLM_FALLBACK. Default: False
keywords: llm fallback tier 3 enable extraction
---

**Environment variable:** `EXTRACTOR_LLM_FALLBACK`

**Default:** `False`


Whether [tier 3](#tier.llm) — extraction via a language model — may run at all.

**Off by default, and deliberately.** Tier 3 spends your provider credit on
every message that triggers it. Turning it on is a decision to pay for better
extraction on messy input.

Turning this on is necessary but not sufficient: tier 3 also needs a provider
key saved for the account, and it only fires when the cheap tiers came up
short. See [tier 3](#tier.llm) for the exact trigger conditions.
