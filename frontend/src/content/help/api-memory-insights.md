---
id: api.memory.insights
title: Dashboard insights
category: api
updated_at: 2026-08-05
summary: Aggregates behind the dashboard charts: fields per namespace, declines by reason over time, and handle lineage.
keywords: insights dashboard charts aggregate namespace declines lineage superseded
---

`GET /api/v1/memory/insights`


Everything the [dashboard](/dashboard) charts are drawn from, in one response,
scoped to the calling account. Three blocks:

- **`namespaces`** — how many fields each section currently holds (`active`)
  and how many values it has retired (`superseded`). One field holds one
  value; a replaced value leaves active state entirely and survives in
  `history`, which is what the superseded count reads.
- **`declines`** — refusals grouped by reason, bucketed by day, plus totals and
  the reasons ranked most common first. Both kinds of refusal count: a value
  the field could not hold (quarantined in `_unmapped`) and a field nobody
  supplied a value for (`unresolved`).
- **`lineage`** — the ordered chain of handles per session, with the field
  count at each step.

**A decline is counted on the version that introduced it.** Quarantine
accumulates down a session, so reading the block as it stands on every version
would report the same refusal again on each later turn and turn a flat line
into a rising one.

This exists so the dashboard makes one request instead of walking
[`/memory/versions`](#api.memory.versions) and then fetching every handle — N+1
requests for anyone with real history. It is read-only and touches no state.

**Scoping.** The account comes from the credential, exactly as everywhere else
here; there is no parameter that widens it. Works with either a console session
or an [API key](#api.apikeys).


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
