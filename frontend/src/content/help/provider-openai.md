---
id: provider.openai
title: OpenAI
category: providers
updated_at: 2026-08-04
summary: A direct connection if you already hold an OpenAI key.
keywords: openai gpt key direct provider
---

**Where to get a key.** platform.openai.com, API keys section.

**How to configure.** API Keys screen, OpenAI card, paste, Save, Test
connection.

**Recommended models.** `gpt-4o-mini` for both chat and
[tier-3 extraction](#tier.llm); it is the cheapest model that reliably returns
strict JSON.

**Base URL.** Defaults to the public API. Override with
[`OPENAI_BASE_URL`](#settings.openai_base_url) if you route through a gateway
or a compatible endpoint.

**What leaves your machine.** Your question, plus the minimal memory subset
StateJar retrieved for it — typically two or three fields. Never your whole
state, and never the raw transcript. Check exactly what was sent in the
[Retrieved Context tab](#ui.tab_retrieved_context) and the
[audit trail](#concept.audit-entry).

**When it is unavailable.** Auth failures, rate limits and unknown models are
translated into plain messages. StateJar never echoes a provider error body
back to you verbatim, because those bodies have been observed to contain the
request — including the key.
