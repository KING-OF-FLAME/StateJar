---
id: settings.jwt_secret
title: JWT_SECRET
category: settings
updated_at: 2026-08-04
summary: Environment variable JWT_SECRET. Default: change-me
keywords: jwt secret token signing auth security
---

**Environment variable:** `JWT_SECRET`

**Default:** `change-me`


The signing secret for session tokens. **Must be changed before deployment.**

If it is left at the default, anyone who knows the default can mint a valid
token for any account. Use at least 32 bytes of random data; shorter keys
produce a warning from the JWT library because HMAC-SHA256 wants 32.

Rotating it invalidates every issued token, logging everyone out. That is the
correct response to a suspected leak.
