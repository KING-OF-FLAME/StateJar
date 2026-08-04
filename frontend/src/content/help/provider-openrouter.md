---
id: provider.openrouter
title: OpenRouter
category: providers
updated_at: 2026-08-04
summary: One key, many models including free ones. The easiest place to start.
keywords: openrouter provider key free models default
---

**Where to get a key.** Sign up at openrouter.ai and create a key in your
account settings.

**How to configure.** API Keys screen, OpenRouter card, paste, Save, then
**Test connection**.

**Recommended models.** StateJar's default is
`openrouter/openai/gpt-4o-mini` — cheap, fast, and reliable at the strict-JSON
extraction [tier 3](#tier.llm) needs. OpenRouter also lists free models, which
is what makes it the practical choice for a first run.

The model id is namespaced deliberately: a bare `openai/gpt-4o-mini` is both a
valid OpenRouter id *and* an OpenAI routing prefix, so StateJar spells out
which one it means rather than depending on precedence.

**What leaves your machine.** Your question, plus the minimal memory subset
StateJar retrieved for it — typically two or three fields. Never your whole
state, and never the raw transcript. Check exactly what was sent in the
[Retrieved Context tab](#ui.tab_retrieved_context) and the
[audit trail](#concept.audit-entry).

**When it is unavailable.** A bad key, a rate limit and an unknown model each
produce a distinct, readable message — never a raw provider payload and never
your key. If tier 3 is configured to use OpenRouter and it fails, the chip goes
amber ([unavailable](#ui.tier_chips)) and the deterministic tiers still run, so
extraction degrades rather than stopping.
