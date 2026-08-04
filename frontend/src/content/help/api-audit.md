---
id: api.audit
title: Audit trail
category: api
updated_at: 2026-08-04
summary: Every disclosure, filterable by session and scope.
keywords: audit trail log list disclosures filter
---

`GET /api/v1/audit`


One row per disclosure: handle used, field keys sent, provider, model, request
id, timestamp.

**Field keys, never values, and never message text.** The trail records what
was disclosed, not what it said. See [audit entry](#concept.audit-entry).


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
