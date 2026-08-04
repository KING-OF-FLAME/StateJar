---
id: api.keys.provider
title: Provider keys
category: api
updated_at: 2026-08-04
summary: Save, list and remove the model-provider keys StateJar calls on your behalf.
keywords: provider keys save list delete encrypted
---

`GET · POST /api/v1/keys/provider · DELETE /api/v1/keys/provider/{provider}`


Keys are encrypted with [`AES_KEY`](#settings.aes_key) before they touch the
database. **The listing returns only the last four characters** and a
`has_key` flag — never the key itself, and never in an error message.

The local [Ollama](#provider.ollama) entry stores a base URL and no key at all,
because a local daemon needs none. Saving one provider never disturbs another.


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
