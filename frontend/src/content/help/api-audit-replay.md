---
id: api.audit.replay
title: Replay a disclosure
category: api
updated_at: 2026-08-04
summary: Reconstruct exactly what was disclosed for one audited response.
keywords: replay audit reconstruct verify disclosure proof
---

`GET /api/v1/audit/{request_id}/replay`


Fetches the state by its handle and re-applies the recorded field keys,
reproducing the exact subset that was sent.

It also re-derives the handle and reports `verified`. If the stored state had
been altered, the re-derived handle would not match and the replay would say
so. That check is what makes the audit trail evidence rather than a log of
claims.


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
