---
id: faq.transcript-storage
title: Where is my chat history stored?
category: faq
updated_at: 2026-08-04
summary: Where is my chat history stored, and why not on the server?
keywords: transcript history stored browser server privacy messages
---

**In your browser, and only there.**

StateJar does not store raw transcripts. This is not an oversight to be fixed
with a messages table — it is the design the product is built on, and the
storage layer refuses transcripts at write time.

So:

- History is **per browser**. The same account on another device shows the same
  *memory* and an empty conversation.
- Clearing site data clears it. Your state survives.
- **Logging out wipes it**, deliberately, so a shared machine does not hand it
  to the next person.

The server keeps the other half of a session's history — provenance, not words.
[`GET /sessions/{id}/turns`](#api.sessions.turns) returns the handle current on
each turn, its parent, the state version, and what was disclosed from it. It
says `contains_message_text: false` in its own response.

Your client holds the words. The server holds the provenance. Joining them is
the caller's job, and that separation is the point.
