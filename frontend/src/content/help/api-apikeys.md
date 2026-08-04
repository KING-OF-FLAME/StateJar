---
id: api.apikeys
title: Your StateJar API keys
category: api
updated_at: 2026-08-04
summary: List the keys you have generated, and revoke one.
keywords: api keys list revoke delete manage
---

`GET /api/v1/apikeys · DELETE /api/v1/apikeys/{key_id}`


The listing never contains a usable key — only an id, a label, a prefix and
timestamps. There is no endpoint that returns a full key after creation,
because a store that can show you a key can show it to whoever reads the
database.

Deleting is immediate. A revoked key fails on its next request.


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
