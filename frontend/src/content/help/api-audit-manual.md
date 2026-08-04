---
id: api.audit.manual
title: Record a client-side disclosure
category: api
updated_at: 2026-08-04
summary: Log a disclosure your client made without going through /chat.
keywords: manual audit client disclosure ollama browser log
---

`POST /api/v1/audit/manual`


Exists for one real case: [browser-direct Ollama](#provider.ollama). The prompt
goes from your browser straight to your own daemon and never touches our
server, so our server cannot log it — but the disclosure still happened and
still belongs in the trail.

The client reports the handle it used and the keys it sent. Marked as
client-reported, because that is what it is.


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
