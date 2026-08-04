---
id: settings.rate_limit_enabled
title: RATE_LIMIT_ENABLED
category: settings
updated_at: 2026-08-04
summary: Environment variable RATE_LIMIT_ENABLED. Default: True
keywords: rate limit throttle requests quota
---

**Environment variable:** `RATE_LIMIT_ENABLED`

**Default:** `True`


Whether per-user request limits are enforced.

Leave it on. Turning it off removes the protection against a runaway client
burning through your provider credit, and StateJar's chat endpoint spends real
money per call.

Set it to `false` only for local load testing, and only locally. See
[rate limit errors](#trouble.rate-limit).
