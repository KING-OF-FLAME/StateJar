---
id: ui.instant_demo
title: The demos
category: interface
updated_at: 2026-08-04
summary: Two scripted runs that exercise the real pipeline with no provider key.
keywords: demo instant scripted run presentation showcase
---

**Short demo** — a six-step scripted run that shows extraction, a handle, a
session hop and minimal retrieval in about a minute. Space advances it; R
restarts; Escape exits.

**Run 17-turn demo** — the longer disaster-relief scenario. See
[the demo scenario](#demo.scenario).

Both call only `/memory/ingest` and `/memory/query`. The user turns and the
replies are fixed in the client, so **no provider key and no LLM call are
involved** — but the memory pipeline underneath is entirely real: real
extraction, real handles, real minimal retrieval, real audit rows.

That is the point of them. They work on a brand-new account with zero keys,
which is the account a judge or a reviewer will have.
