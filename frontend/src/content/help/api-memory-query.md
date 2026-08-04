---
id: api.memory.query
title: Query memory
category: api
updated_at: 2026-08-04
summary: Retrieve the minimal subset relevant to a question. No model call.
keywords: query retrieve subset minimal disclosure read
---

`POST /api/v1/memory/query`


Read-only. Returns the fields a question actually needs, plus metadata: how
many fields were dropped, the retrieval mode, and the
[savings figure](#concept.token-savings).

Use it to see what *would* be disclosed without spending a model call, or to
build your own prompt around the subset.

By default it writes **no audit row**, because nothing left the system. Pass
`audit: true` when your client is the one making the disclosure — see
[the manual audit endpoint](#api.audit.manual).


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
