---
id: ui.dashboard
title: Dashboard
category: interface
updated_at: 2026-08-04
summary: Account-level counts and the most recent savings figure.
keywords: dashboard stats counts home overview
---

Four cards:

- **Sessions** — how many session tags you have used.
- **Memory states** — how many states you have written. Every accepted turn
  writes one, so this is roughly your turn count with facts in it.
- **Audit entries** — how many disclosures have been made.
- **Tokens saved (last chat)** — the retriever's figure for your most recent
  query, measured against the **disclosable state**, not against a transcript
  replay. The card says so underneath. See
  [token savings](#concept.token-savings).

All four come from `GET /memory/stats`. See
[that endpoint](#api.memory.stats).
