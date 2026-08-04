---
id: api.usage
title: Usage
category: api
updated_at: 2026-08-04
summary: Aggregate disclosure volume across your audited calls.
keywords: usage tokens aggregate volume estimate
---

`GET /api/v1/usage`


Sums the retriever's work over every audited call: how much was disclosed, and
an estimate of what was saved against the disclosable baseline.

An estimate, and labelled as one — it is derived from stored field keys and
sizes, not from a provider's billing.


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
