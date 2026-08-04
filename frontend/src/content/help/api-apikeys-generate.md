---
id: api.apikeys.generate
title: Generate a StateJar API key
category: api
updated_at: 2026-08-04
summary: Create a key for calling StateJar from your own code. Shown once.
keywords: generate api key create secret once
---

`POST /api/v1/apikeys/generate`


**The full key is returned exactly once, in this response.** It is stored
hashed, so it cannot be retrieved later. If you lose it, generate another and
delete the old one.

Use these rather than a login token for anything running unattended.


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
