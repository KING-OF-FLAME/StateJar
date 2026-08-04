---
id: api.memory.ingest
title: Ingest a message
category: api
updated_at: 2026-08-04
summary: Run the memory pipeline on a message: extract, canonicalize, hash, store.
keywords: ingest write store message extract pipeline
---

`POST /api/v1/memory/ingest`


The main write endpoint, and the one to reach for first. Given a session tag
and some text it runs extraction through the [tiers](#concept.extraction-tier),
canonicalizes what they produced, derives a [handle](#concept.handle), and
stores the new state as a child of the previous one.

The response carries the new state, its handle, its parent, any conflicts, and
**metadata that is deliberately outside `state`**: which tiers ran, what each
contributed, and any notice. Keeping that outside the state is not tidiness —
anything inside `state` reaches the hash, and a handle that moved because a
tier happened to be installed would not be a content address at all.

**No provider key is required.** Ingest never calls a model unless
[tier 3](#tier.llm) is enabled and triggers.


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
