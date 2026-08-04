---
id: trouble.deep-extraction-unavailable
title: Amber 'unavailable' chip
category: troubleshooting
updated_at: 2026-08-04
summary: A tier chip is amber and reads *unavailable*.
keywords: amber unavailable chip tier failed deep extraction timeout
---

**Symptom.** A tier chip is amber and reads *unavailable*.

**Likely cause.** That tier was **attempted and did not answer** — which is deliberately
distinguished from a tier that was skipped. Something went wrong reaching it: a
missing or invalid provider key, a rate limit, a timeout (tier 3 gives up after
8 seconds), or every model in the
[fallback chain](#settings.extractor_llm_fallback_models) failing in turn.

**Fix.** Open the API Keys screen and press **Test connection** on the provider
tier 3 is configured to use — that reports the real cause in plain language. If
the key is fine, the likeliest remaining causes are a rate limit or a slow
provider; the timeout is short on purpose so extraction degrades rather than
stalling a turn.

Your state is still valid either way. The deterministic tiers ran, and
everything they produced went through the same guards.
