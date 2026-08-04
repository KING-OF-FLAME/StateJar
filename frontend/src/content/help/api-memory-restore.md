---
id: api.memory.restore
title: Restore a handle
category: api
updated_at: 2026-08-04
summary: Adopt a sealed state into a session, verifying it on the way in.
keywords: restore handle adopt load verify cross session
---

`POST /api/v1/memory/restore`


Re-derives the handle from the stored state and **refuses if the two disagree**.
A restore that succeeds is therefore a verification: the bytes are what they
claimed to be.

This is how memory crosses a session boundary. See
[your first handle restore](#gs.first-handle-restore).


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
