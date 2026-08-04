---
id: api.keys.provider.test
title: Test a provider connection
category: api
updated_at: 2026-08-04
summary: Check a saved key really works, before you need it live.
keywords: test connection provider check verify key
---

`POST /api/v1/keys/provider/{provider}/test`


Actually calls the provider and reports what happened, in plain language: a bad
key, a rate limit, an unknown model, or an unreachable address. It never
returns the provider's raw error body — those bodies have been observed to echo
the request, including the key.

Worth pressing before a demo. A key that was pasted with a trailing space fails
here in three seconds instead of on stage.


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
