---
id: api.chat
title: Chat
category: api
updated_at: 2026-08-04
summary: Query, then send the subset to a model and return its reply.
keywords: chat completion model reply ask llm
---

`POST /api/v1/chat`


Composes [query](#api.memory.query) and a provider call: retrieve the minimal
subset, build a prompt from it, call the model you named, write an
[audit row](#concept.audit-entry), return the reply.

**The raw transcript is never sent.** What the model receives is the retrieved
subset and the current turn.

Requires a provider key. Upstream failures are translated into readable errors
with an appropriate status — a provider 5xx becomes a 502, a timeout becomes a
502, never a leaked payload.


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
