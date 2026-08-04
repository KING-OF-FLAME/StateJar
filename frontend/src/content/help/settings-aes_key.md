---
id: settings.aes_key
title: AES_KEY
category: settings
updated_at: 2026-08-04
summary: Environment variable AES_KEY. Default: change-me-32-bytes-key-required!
keywords: aes encryption key provider secrets security
---

**Environment variable:** `AES_KEY`

**Default:** `change-me-32-bytes-key-required!`


The key that encrypts stored provider keys. **Must be changed before
deployment,** and must be exactly 32 bytes.

Provider keys are encrypted with this before they touch the database and are
never returned by the API — the listing shows only the last four characters.

**Rotating it makes existing stored provider keys undecryptable.** They cannot
be recovered; users have to re-enter them. Plan for that before changing it.
