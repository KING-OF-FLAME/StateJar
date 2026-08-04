---
id: api.memory.stats
title: Account stats
category: api
updated_at: 2026-08-04
summary: Counts for the Dashboard, plus the last chat's savings figure.
keywords: stats dashboard counts metrics summary
---

`GET /api/v1/memory/stats`


Session count, state count, audit count, and `token_saved_pct` for your most
recent query.

That percentage is measured against the **disclosable state**, not a transcript
replay, and is clamped at zero. See
[token savings and its baseline](#concept.token-savings).


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
