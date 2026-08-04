---
id: api.memory.state
title: Read a state by handle
category: api
updated_at: 2026-08-04
summary: Fetch the exact state a handle addresses.
keywords: state handle read fetch get by hash
---

`GET /api/v1/memory/state/{handle}`


The read side of content addressing. Given a handle, return that state — the
same bytes that hashed to it.

Scoped to your account: a handle belonging to someone else is not readable,
even though the handle itself is just a hash.


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
