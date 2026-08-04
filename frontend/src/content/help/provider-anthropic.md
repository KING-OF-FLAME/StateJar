---
id: provider.anthropic
title: Anthropic
category: providers
updated_at: 2026-08-04
summary: Claude models, direct.
keywords: anthropic claude key provider haiku
---

**Where to get a key.** console.anthropic.com, API keys.

**How to configure.** API Keys screen, Anthropic card, paste, Save, Test
connection.

**Recommended models.** Claude Haiku for extraction work, where cost and
latency matter and the task is structured; a larger Claude for the
conversation itself if the answers need reasoning.

**Base URL.** [`ANTHROPIC_BASE_URL`](#settings.anthropic_base_url) if you need
to point elsewhere.

**What leaves your machine.** Your question, plus the minimal memory subset
StateJar retrieved for it — typically two or three fields. Never your whole
state, and never the raw transcript. Check exactly what was sent in the
[Retrieved Context tab](#ui.tab_retrieved_context) and the
[audit trail](#concept.audit-entry).

**When it is unavailable.** Same handling as every other provider: a clear
message naming the cause, never the key. If Anthropic is your
[tier-3 fallback](#settings.extractor_llm_fallback_models), StateJar tries the
next model in the chain before giving up and marking the tier unavailable.
