---
id: trouble.rate-limit
title: Rate limit errors
category: troubleshooting
updated_at: 2026-08-04
summary: A request fails with a rate-limit error.
keywords: rate limit 429 too many requests throttle quota
---

**Symptom.** A request fails with a rate-limit error.

**Likely cause.** Either StateJar's own per-user limit, or your model provider's.

StateJar's limit exists because the chat endpoint spends real money per call
and a runaway client would otherwise burn through your provider credit. It is
controlled by [`RATE_LIMIT_ENABLED`](#settings.rate_limit_enabled).

A provider's limit is theirs, and the message will name the provider.

**Fix.** Slow down and retry. For a provider limit, configure a
[fallback chain](#settings.extractor_llm_fallback_models) so extraction moves
to another model instead of failing. Do not disable StateJar's limit on a
deployment that faces the internet — the protection is the point.
