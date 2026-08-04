---
id: ui.message_box
title: Message box
category: interface
updated_at: 2026-08-04
summary: Where you type. Every message goes through the full pipeline.
keywords: message input box type send chat compose
---

Enter sends. Each message runs `/memory/ingest` first — extraction,
canonicalization, handle, store — and then `/memory/query` and `/chat` to
produce a reply.

Because ingest is separate, **the memory pipeline works without a provider
key**. With no key configured you will see the state update and the panels
fill; only the model's reply will report that no provider is set.

A message with no facts in it is normal and stores nothing. See
[reading the Memory State panel](#gs.reading-memory-state).
