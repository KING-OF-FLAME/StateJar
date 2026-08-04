---
id: api.sessions.turns
title: Session turns
category: api
updated_at: 2026-08-04
summary: Per-turn provenance for a session. Contains no message text, by design.
keywords: turns session history provenance transcript messages
---

`GET /api/v1/sessions/{session_id}/turns`


Returns, for each turn: the handle that was current, its parent, the state
version, when it happened, and what was disclosed from it.

**It is not a transcript endpoint and never will be.** StateJar does not store
raw transcripts — the storage layer refuses them at write time — so there is no
message text to return. The response says so explicitly with
`contains_message_text: false`.

The division is the point: your client holds the words, the server holds the
provenance, and joining them is the caller's job. See
[the FAQ](#faq.transcript-storage).


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
