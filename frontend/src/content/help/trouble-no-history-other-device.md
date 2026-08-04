---
id: trouble.no-history-other-device
title: Chat history missing on another device
category: troubleshooting
updated_at: 2026-08-04
summary: You sign in elsewhere and the memory is there but the conversation is gone.
keywords: history missing device transcript gone browser lost chat
---

**Symptom.** You sign in elsewhere and the memory is there but the conversation is gone.

**Likely cause.** Working as designed. StateJar never stores raw transcripts — the storage
layer refuses them at write time — so the words live only in the browser that
typed them. Only *state* travels.

Clearing site data, or logging out, also clears them. Logging out does so
deliberately: a shared machine must not hand the next person the last person's
conversation.

**Fix.** Nothing to fix. If you need the provenance of past turns — which handle
was current, what was disclosed — that **is** available from the server:
[`GET /sessions/{id}/turns`](#api.sessions.turns). To move the memory itself,
copy a handle and [restore it](#ui.restore_handle). See
[the FAQ](#faq.transcript-storage).
