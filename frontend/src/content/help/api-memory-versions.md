---
id: api.memory.versions
title: List state versions
category: api
updated_at: 2026-08-04
summary: Every handle in a session's chain, oldest to newest.
keywords: versions handles chain lineage list history
---

`GET /api/v1/memory/versions`


The lineage behind the [Handles tab](#ui.tab_handles). Each entry is one
version; the newest is the session's current state.

State is append-only — a version is never rewritten — so this list only ever
grows. See [active state vs history](#concept.active-vs-history).


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
