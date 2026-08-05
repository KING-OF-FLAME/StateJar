---
id: api.memory.query
title: Query memory
category: api
updated_at: 2026-08-05
summary: Retrieve the minimal subset relevant to a question, plus a prompt-ready context string. No model call.
keywords: query retrieve subset minimal disclosure read sidecar memory_context own llm
---

`POST /api/v1/memory/query`


Read-only. Returns the fields a question actually needs, plus metadata: how
many fields were dropped, the retrieval mode, and the
[savings figure](#concept.token-savings).

Use it to see what *would* be disclosed without spending a model call, or to
build your own prompt around the subset.

**Bringing your own LLM.** The response also carries `memory_context`: the same
subset already formatted for a system message, built by the same function
[`POST /chat`](#api.chat) uses. Drop it in as your `system` message, send your
own request to your own provider with your own key, and you get the context the
built-in path would have used — identical by construction, rather than by two
places happening to agree. `subset` is still there if you would rather format
it yourself. A runnable example lives at `examples/sidecar_openai.py`.

**Call order matters.** Ingest the user's message *before* you query: ingest
commits before it returns, so the context you get back already contains the
turn that was just sent. Query first — or ingest in the background — and a
question that depends on the message asking it retrieves state from before that
message existed. You still get a fluent answer; it is just built on stale
memory, which is the kind of wrong that does not announce itself.

By default it writes **no audit row**, because nothing left the system. Pass
`audit: true` when your client is the one making the disclosure — see
[the manual audit endpoint](#api.audit.manual).


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
