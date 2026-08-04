---
id: provider.gemini
title: Google (Gemini)
category: providers
updated_at: 2026-08-04
summary: Google's models, direct.
keywords: google gemini key provider flash
---

**Where to get a key.** Google AI Studio.

**How to configure.** API Keys screen, Google card, paste, Save, Test
connection.

**Recommended models.** A Flash-class model for extraction and for most chat;
they are the cost and latency match for what StateJar asks of a model.

**Base URL.** [`GEMINI_BASE_URL`](#settings.gemini_base_url).

**What leaves your machine.** Your question, plus the minimal memory subset
StateJar retrieved for it — typically two or three fields. Never your whole
state, and never the raw transcript. Check exactly what was sent in the
[Retrieved Context tab](#ui.tab_retrieved_context) and the
[audit trail](#concept.audit-entry).

**When it is unavailable.** Reported as a readable message. Note that Google's
API returns some quota errors with a 200 status and an error body, so StateJar
inspects the body rather than trusting the status code — a "success" that
contains an error is still treated as a failure.
